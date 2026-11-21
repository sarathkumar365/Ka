import threading
from datetime import datetime

import pytest

from server.finance.drive_inbox import approve_statement, sync_drive
from server.finance.store import CsvFinanceStore
from server.memory.pending import PendingError
from server.store.db import Db
from tests.finance.test_importer import ROWS
from tests.fixtures.statement_pdf import StatementSpec, build_statement
from tests.integrations.fakes import FakeDrive

NOW = datetime(2031, 4, 24, 9, 0)


@pytest.fixture
def setup(ctx, tmp_path):
    pdf = tmp_path / "src.pdf"
    build_statement(pdf, StatementSpec(rows=ROWS))
    from server.config import GoogleConfig

    cfg = ctx.config.model_copy(
        update={
            "google": GoogleConfig(
                client_file=tmp_path / "c.json", drive_folder_id="F", sheet_id="S"
            )
        }
    )
    return cfg, Db(tmp_path / "k.db"), pdf.read_bytes()


def statements(db):
    return [c for c in db.list_pending() if c.kind == "statement"]


def test_sync_queues_card_and_marks_seen(setup):
    cfg, db, body = setup
    drive = FakeDrive({"d1": ("Statement.pdf", body)})
    r = sync_drive(drive, cfg, db, NOW)
    assert r.new == 1 and r.skipped == []
    card = statements(db)[0].payload
    assert card["rows"] == 2 and card["checks"] == [] and card["already_imported"] is False
    assert card["money_in"] == "1250.00"
    assert sync_drive(drive, cfg, db, NOW).new == 0
    assert drive.downloads == ["d1"]


def test_non_statement_is_skipped_once(setup):
    cfg, db, _ = setup
    drive = FakeDrive({"x": ("photo.pdf", b"%PDF-1.4 not a statement")})
    assert len(sync_drive(drive, cfg, db, NOW).skipped) == 1
    assert sync_drive(drive, cfg, db, NOW).skipped == []
    assert statements(db) == []


def test_second_copy_shows_already_imported(setup):
    cfg, db, body = setup
    sync_drive(FakeDrive({"d1": ("a.pdf", body)}), cfg, db, NOW)
    store = CsvFinanceStore(cfg.finance_dir)
    assert "2 rows" in approve_statement(statements(db)[0].id, cfg, db, store)
    sync_drive(FakeDrive({"d1": ("a.pdf", body), "d2": ("a copy.pdf", body)}), cfg, db, NOW)
    copy = statements(db)[-1]
    assert copy.payload["already_imported"] is True
    with pytest.raises(PendingError, match="already imported"):
        approve_statement(copy.id, cfg, db, store)
    assert len(store.transactions()) == 2


def test_concurrent_syncs_queue_one_card(setup):
    cfg, _, body = setup
    drive = FakeDrive({"d1": ("a.pdf", body)})
    ts = [
        threading.Thread(target=lambda: sync_drive(drive, cfg, Db(cfg.db_path, cfg.user_id), NOW))
        for _ in range(2)
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(statements(Db(cfg.db_path, cfg.user_id))) == 1


def test_two_copies_before_approval_second_closes(setup):
    cfg, db, body = setup
    sync_drive(FakeDrive({"d1": ("a.pdf", body), "d2": ("b.pdf", body)}), cfg, db, NOW)
    first, second = statements(db)
    store = CsvFinanceStore(cfg.finance_dir)
    approve_statement(first.id, cfg, db, store)
    from server.finance.drive_inbox import refresh_imported

    rows = refresh_imported([second.payload | {"id": second.id}], store)
    assert rows[0]["already_imported"] is True
    with pytest.raises(PendingError, match="already imported"):
        approve_statement(second.id, cfg, db, store)
    assert db.get_pending(second.id).status == "rejected"


def test_one_failing_download_does_not_block_the_rest(setup):
    cfg, db, body = setup

    class Flaky(FakeDrive):
        def download(self, file_id, dest):
            if file_id == "bad":
                raise OSError("403 cannotDownloadAbusiveFile")
            return super().download(file_id, dest)

    r = sync_drive(Flaky({"bad": ("x.pdf", b""), "d1": ("a.pdf", body)}), cfg, db, NOW)
    assert r.new == 1 and len(r.skipped) == 1
    assert [p.name for p in cfg.statements_dir.iterdir()] == ["a.pdf"]
