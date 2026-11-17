from datetime import datetime

from server.finance.sheet_copy import push_sheet
from server.finance.store import CsvFinanceStore
from server.store.db import Db
from tests.finance.test_store import STATEMENT, tx
from tests.integrations.fakes import FakeSheets

NOW = datetime(2031, 4, 24, 9, 0)


def test_push_writes_all_rows_as_text(ctx, tmp_path):
    store = CsvFinanceStore(tmp_path / "fin")
    store.add_import(STATEMENT, [tx(1)])
    sheets, db = FakeSheets(), Db(":memory:")
    assert push_sheet(sheets, "S", store, db, NOW) is True
    header, row = sheets.tabs["Transactions"]
    assert row[header.index("amount")] == "-1250.00"
    assert len(sheets.tabs["Statements"]) == 2
    assert db.get_state("sheet_status").startswith('{"at"')


def test_push_failure_keeps_csv_and_records_error(tmp_path):
    store = CsvFinanceStore(tmp_path / "fin")
    store.add_import(STATEMENT, [tx(1)])
    db = Db(":memory:")
    assert push_sheet(FakeSheets(fail=OSError("sheet gone")), "S", store, db, NOW) is False
    assert len(store.transactions()) == 1
    assert "sheet gone" in db.get_state("sheet_status")


def test_copies_do_not_overlap(ctx, tmp_path, monkeypatch):
    import threading
    import time

    import server.finance.sheet_copy as sc

    inside, peak = [0], [0]

    def slow(*a, **k):
        inside[0] += 1
        peak[0] = max(peak[0], inside[0])
        time.sleep(0.1)
        inside[0] -= 1
        return True

    monkeypatch.setattr(sc, "_push_locked", slow)
    from server.config import GoogleConfig

    g = GoogleConfig(client_file=tmp_path / "c.json", drive_folder_id="F", sheet_id="S")
    cfg = ctx.config.model_copy(update={"flags": {"google": True}, "google": g})
    ts = [threading.Thread(target=sc.push_from_config, args=(cfg,)) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak[0] == 1
