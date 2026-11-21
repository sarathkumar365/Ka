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
    db = Db(cfg.db_path, cfg.user_id)
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


def test_onboarding_job_runs_only_what_was_given(setup):
    from server.intake.runner import run_onboarding_job

    cfg, db, _ = setup
    job = db.new_intake_job("onboarding", NOW)
    items = json.dumps([{"type": "fact", "text": "Speaks French"}])
    run_onboarding_job(
        job, [], None, [("claude", "pasted")], cfg, FakeAdapter([Reply(text=items)]), lambda: NOW
    )
    got = db.get_intake_job(job)
    assert got.status == "done"
    assert got.result["memories"] == 1 and got.result["jobs"] == 0


def test_onboarding_job_all_parts(setup):
    from server.agent.adapters import AdapterError
    from server.intake.runner import Basics, run_onboarding_job

    cfg, db, resume = setup
    job = db.new_intake_job("onboarding", NOW)

    class Script:
        def __init__(self):
            self.n = 0

        def complete(self, messages, tools):
            self.n += 1
            if self.n == 1:
                return Reply(text=GOOD)
            if self.n == 2:
                return Reply(text=json.dumps([{"type": "fact", "text": "Likes chess"}]))
            raise AdapterError("timeout")

    basics = Basics(name="Avery Quinn", city="Newtown", region="", country="", role="Engineer")
    sources = [("claude", "a"), ("chatgpt", "b")]
    run_onboarding_job(job, [resume], basics, sources, cfg, Script(), lambda: NOW)
    got = db.get_intake_job(job)
    assert got.status == "done"
    assert got.result["jobs"] == 1 and got.result["memories"] == 1
    assert any("chatgpt" in w for w in got.result["warnings"])
    assert any(c.payload.get("section") == "basics" for c in db.list_pending())
    assert not resume.exists()


def test_onboarding_job_nothing_usable_fails(setup, tmp_path):
    from server.agent.adapters import AdapterError
    from server.intake.runner import run_onboarding_job

    cfg, db, _ = setup
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"not a pdf")
    job = db.new_intake_job("onboarding", NOW)

    class Down:
        def complete(self, messages, tools):
            raise AdapterError("down")

    run_onboarding_job(job, [bad], None, [("claude", "a")], cfg, Down(), lambda: NOW)
    assert db.get_intake_job(job).status == "failed"


def test_onboarding_basics_name_wins_over_resume_name(setup):
    from server.intake.runner import Basics, run_onboarding_job

    cfg, db, resume = setup
    job = db.new_intake_job("onboarding", NOW)
    basics = Basics(name="Avery Q", city="", region="", country="", role="")
    other = json.loads(GOOD)
    other["profile"]["name"] = "A. Quinn"
    reply = Reply(text=json.dumps(other))
    run_onboarding_job(job, [resume], basics, [], cfg, FakeAdapter([reply]), lambda: NOW)
    names = [
        i
        for c in db.list_pending()
        if c.payload.get("section") == "basics"
        for i in c.payload["items"]
        if i["label"].lower().startswith("name")
    ]
    assert len(names) == 1


def test_onboarding_job_nothing_new_is_done_not_failed(setup):
    from server.intake.runner import run_onboarding_job

    cfg, db, _ = setup
    job = db.new_intake_job("onboarding", NOW)
    run_onboarding_job(
        job, [], None, [("claude", "small talk")], cfg, FakeAdapter([Reply(text="[]")]), lambda: NOW
    )
    got = db.get_intake_job(job)
    assert got.status == "done" and got.result["memories"] == 0


def test_onboarding_job_reports_each_part(setup):
    from server.agent.adapters import AdapterError
    from server.intake.runner import Basics, run_onboarding_job

    cfg, db, resume = setup
    job = db.new_intake_job("onboarding", NOW)

    class Script:
        n = 0

        def complete(self, messages, tools):
            Script.n += 1
            if Script.n == 1:
                return Reply(text=GOOD)
            raise AdapterError("down")

    basics = Basics(name="Avery Q", city="", region="", country="", role="")
    run_onboarding_job(job, [resume], basics, [("claude", "a")], cfg, Script(), lambda: NOW)
    parts = db.get_intake_job(job).result["parts"]
    assert parts == [
        {"label": "Basics", "state": "done"},
        {"label": "resume.txt", "state": "done"},
        {"label": "claude", "state": "failed"},
    ]


def test_onboarding_parts_without_basics(setup):
    from server.intake.runner import run_onboarding_job

    cfg, db, resume = setup
    job = db.new_intake_job("onboarding", NOW)
    items = json.dumps([{"type": "fact", "text": "Likes tea"}])
    adapter = FakeAdapter([Reply(text=GOOD), Reply(text=items)])
    run_onboarding_job(job, [resume], None, [("chatgpt", "a")], cfg, adapter, lambda: NOW)
    parts = db.get_intake_job(job).result["parts"]
    assert parts == [
        {"label": "resume.txt", "state": "done"},
        {"label": "chatgpt", "state": "done"},
    ]
