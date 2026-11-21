from datetime import date, timedelta

from server.agent.adapters import AdapterError
from server.config import Config
from server.scheduler import LAST_DAY, catch_up_extraction, nightly_job
from server.store.db import Db
from tests.conftest import add_account

TODAY = date(2031, 4, 10)


def test_catch_up_runs_each_missed_day_once(ctx):
    db = Db(":memory:")
    db.set_state(LAST_DAY, (TODAY - timedelta(days=3)).isoformat())
    days: list[date] = []

    def extract(day, db, data, adapter, now, **k):
        days.append(day)
        return 0

    ran = catch_up_extraction(ctx.config, db, lambda: object(), TODAY, extract=extract)
    assert ran == [date(2031, 4, 8), date(2031, 4, 9)] == days
    assert catch_up_extraction(ctx.config, db, lambda: object(), TODAY, extract=extract) == []


def test_first_run_and_long_gap_are_bounded(ctx):
    db = Db(":memory:")
    seen: list[date] = []
    catch_up_extraction(
        ctx.config, db, lambda: object(), TODAY, extract=lambda d, *a, **k: seen.append(d)
    )
    assert seen == [TODAY - timedelta(days=1)]
    db.set_state(LAST_DAY, (TODAY - timedelta(days=30)).isoformat())
    seen.clear()
    catch_up_extraction(
        ctx.config, db, lambda: object(), TODAY, extract=lambda d, *a, **k: seen.append(d)
    )
    assert len(seen) == 7 and seen[-1] == TODAY - timedelta(days=1)


def test_failed_run_logs_and_survives(tmp_path, ctx):
    cfg = Config(data_repo=ctx.config.data_repo, flags={"nightly_extraction": True})

    def broken():
        raise AdapterError("OPENAI_API_KEY not set")

    job = nightly_job(cfg, broken, today=lambda: TODAY)
    job.run()  # must not raise
    db = Db(cfg.db_path, cfg.user_id)
    assert any("extraction failed" in a.text for a in db.list_activity(10))
    assert db.get_state(LAST_DAY) is None


def test_app_starts_scheduler_only_when_asked(ctx):
    from fastapi.testclient import TestClient

    from server.api.app import create_app

    cfg = ctx.config.model_copy(update={"flags": {"nightly_extraction": True}})
    add_account(cfg)
    calls: list[int] = []

    def factory():
        calls.append(1)
        raise AdapterError("no key")

    with TestClient(create_app(cfg, factory, start_scheduler=True)):
        import time

        for _ in range(50):
            if calls:
                break
            time.sleep(0.05)
    assert calls  # catch-up ran in the background and its failure did not stop the app


def test_provider_outage_does_not_mark_day_done(ctx):
    from datetime import datetime as dt

    cfg = Config(data_repo=ctx.config.data_repo, flags={"nightly_extraction": True})
    db = Db(cfg.db_path, cfg.user_id)
    cid = db.new_conversation(dt(2031, 4, 9, 10, 0))
    db.add_message(cid, {"role": "user", "content": "I moved"}, dt(2031, 4, 9, 10, 0))
    db.conn.close()

    class Down:
        def complete(self, messages, tools):
            raise AdapterError("provider timeout")

    nightly_job(cfg, lambda: Down(), today=lambda: TODAY).run()
    db = Db(cfg.db_path, cfg.user_id)
    assert db.get_state(LAST_DAY) is None
    assert any("extraction failed" in a.text for a in db.list_activity(10))


def test_overlapping_runs_extract_each_day_once(ctx, monkeypatch):
    import threading
    import time

    import server.scheduler as sched

    cfg = Config(data_repo=ctx.config.data_repo, flags={"nightly_extraction": True})
    days: list = []

    def slow(day, *a, **k):
        time.sleep(0.2)
        days.append(day)

    monkeypatch.setattr(sched, "extract_memories", slow)
    job = nightly_job(cfg, lambda: object(), today=lambda: TODAY)
    threads = [threading.Thread(target=job.run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert days == [TODAY - timedelta(days=1)]


def test_cron_runs_late_after_sleep():
    from server.scheduler import start_scheduler

    s = start_scheduler([nightly_job(Config(data_repo="."), lambda: object())])
    try:
        assert s.get_job("nightly_extraction").misfire_grace_time is None
    finally:
        s.shutdown(wait=False)


def test_db_failure_does_not_disable_later_runs(ctx, monkeypatch):
    import server.scheduler as sched

    cfg = Config(data_repo=ctx.config.data_repo, flags={"nightly_extraction": True})
    job = nightly_job(cfg, lambda: object(), today=lambda: TODAY)
    real = sched.Db
    monkeypatch.setattr(sched, "Db", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    job.run()
    monkeypatch.setattr(sched, "Db", real)
    seen: list = []
    monkeypatch.setattr(sched, "extract_memories", lambda d, *a, **k: seen.append(d))
    job.run()
    assert seen == [TODAY - timedelta(days=1)]
