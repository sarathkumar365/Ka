import json
from datetime import datetime

import pytest

from server.agent.adapters.base import Reply
from server.agent.adapters.fake import FakeAdapter
from server.config import Config
from server.intake.runner import run_documents_job, run_memory_job
from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0)
GOOD = json.dumps(
    {
        "profile": {"name": "Avery Quinn"},
        "domains": ["Robotics"],
        "jobs": [{"company": "Globex Corp", "position": "Engineer", "start": "2024-02"}],
    }
)


@pytest.fixture
def setup(ctx, tmp_path):
    cfg: Config = ctx.config
    db = Db(cfg.db_path)
    resume = tmp_path / "resume.txt"
    resume.write_text("Avery Quinn. Globex Corp, Engineer, 2024-02 to now.")
    return cfg, db, resume


def start(db):
    return db.new_intake_job("documents", NOW)


def test_documents_job_done_queues_cards_and_deletes_files(setup):
    cfg, db, resume = setup
    job = start(db)
    run_documents_job(job, [resume], cfg, FakeAdapter([Reply(text=GOOD)]), lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "done" and got.result["cards"] >= 2
    assert not resume.exists()
    assert {i.kind for i in db.list_pending()} == {"bundle"}


def test_model_failure_marks_job_failed_with_message_and_cleans_up(setup):
    cfg, db, resume = setup
    job = start(db)
    run_documents_job(
        job, [resume], cfg, FakeAdapter([Reply(text="no"), Reply(text="no")]), lambda: NOW
    )
    got = db.get_intake_job(job)
    assert got.status == "failed" and "usable data" in got.message
    assert db.list_pending() == [] and not resume.exists()


def test_unexpected_error_is_generic_and_does_not_stick(setup):
    cfg, db, resume = setup

    class Boom:
        def complete(self, messages, tools):
            raise RuntimeError("secret path /Users/x")

    job = start(db)
    run_documents_job(job, [resume], cfg, Boom(), lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "failed" and got.message == "Something went wrong."
    assert db.running_intake_job() is None


def test_unsupported_file_fails_readably_and_statement_pdf_is_skipped(setup, tmp_path):
    from datetime import date
    from decimal import Decimal

    from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement

    cfg, db, resume = setup
    stmt = tmp_path / "s.pdf"
    rows = [SpecRow(date(2031, 3, 25), "Point of sale purchase", "Apos Cafe", Decimal("-4.50"))]
    build_statement(stmt, StatementSpec(rows=rows))
    job = start(db)
    run_documents_job(job, [stmt, resume], cfg, FakeAdapter([Reply(text=GOOD)]), lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "done"
    assert any("statement" in w for w in got.result["warnings"])
    assert not stmt.exists()


def test_interrupted_jobs_are_failed_at_startup(setup):
    _, db, _ = setup
    job = start(db)
    db.update_intake_job(job, status="running")
    assert db.running_intake_job() == job
    assert db.fail_interrupted_intake_jobs() == 1
    got = db.get_intake_job(job)
    assert got.status == "failed" and got.message == "interrupted"
    assert db.running_intake_job() is None


def test_memory_job_done(setup):
    cfg, db, _ = setup
    job = db.new_intake_job("memory", NOW)
    items = json.dumps([{"type": "fact", "text": "Speaks French", "replaces": None}])
    run_memory_job(job, [("claude", "pasted")], cfg, FakeAdapter([Reply(text=items)]), lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "done" and got.result["cards"] == 1


def test_memory_job_several_assistants(setup):
    from server.agent.adapters import AdapterError

    cfg, db, _ = setup
    job = db.new_intake_job("memory", NOW)

    class Script:
        def __init__(self):
            self.calls = []

        def complete(self, messages, tools):
            self.calls.append(messages)
            if len(self.calls) == 2:
                raise AdapterError("timeout")
            return Reply(text=json.dumps([{"type": "fact", "text": f"Fact {len(self.calls)}"}]))

    adapter = Script()
    sources = [("claude", "a"), ("gemini", "b"), ("chatgpt", "c")]
    run_memory_job(job, sources, cfg, adapter, lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "done" and got.result["cards"] == 2
    assert any("gemini" in w for w in got.result["warnings"])
    assert "Fact 1" in adapter.calls[2][0]["content"]  # later sources see earlier items
    sources_seen = {i.source for i in db.list_pending()}
    assert sources_seen == {"import:claude", "import:chatgpt"}


def test_memory_job_all_sources_fail(setup):
    from server.agent.adapters import AdapterError

    cfg, db, _ = setup
    job = db.new_intake_job("memory", NOW)

    class Down:
        def complete(self, messages, tools):
            raise AdapterError("down")

    run_memory_job(job, [("claude", "a"), ("chatgpt", "b")], cfg, Down(), lambda: NOW)
    assert db.get_intake_job(job).status == "failed"


def test_second_file_failing_queues_nothing(setup, tmp_path):
    cfg, db, resume = setup
    second = tmp_path / "other.txt"
    second.write_text("more text")
    job = start(db)
    adapter = FakeAdapter([Reply(text=GOOD), Reply(text="junk"), Reply(text="junk")])
    run_documents_job(job, [resume, second], cfg, adapter, lambda: NOW)
    assert db.get_intake_job(job).status == "failed"
    assert db.list_pending() == []
