from dataclasses import dataclass
from datetime import datetime

import pytest

from server.config import GoogleConfig
from server.finance.store import CsvFinanceStore
from server.loops.builtin import ensure_builtin_tasks, statement_import_body
from server.loops.runner import run_task
from server.loops.tasks import TaskStore
from server.loops.triggers import to_apscheduler
from server.store.db import Db
from tests.finance.test_importer import ROWS
from tests.fixtures.statement_pdf import StatementSpec, build_statement
from tests.integrations.fakes import FakeDrive

NOW = datetime(2031, 4, 24, 9, 0)


@dataclass
class Env:
    cfg: object
    db: Db
    drive: FakeDrive
    store: CsvFinanceStore
    good: bytes
    bad: bytes


@pytest.fixture
def env(ctx, tmp_path):
    good, bad = tmp_path / "good.pdf", tmp_path / "bad.pdf"
    build_statement(good, StatementSpec(rows=ROWS))
    from decimal import Decimal

    build_statement(bad, StatementSpec(rows=ROWS, closing_balance=Decimal("1.00")))
    cfg = ctx.config.model_copy(update={"google": GoogleConfig(client_file=tmp_path / "c.json", drive_folder_id="F", sheet_id="S")})
    db = Db(tmp_path / "k.db", cfg.user_id)
    return Env(cfg, db, FakeDrive({}), CsvFinanceStore(cfg.finance_dir, cfg.user_id), good.read_bytes(), bad.read_bytes())


def run_once(env, mode="shadow"):
    store = TaskStore(env.db)
    ensure_builtin_tasks(store, NOW)
    tid = f"{env.cfg.user_id}:statement_import"
    store.set_mode(tid, mode)
    task = store.get(tid)
    run_id = run_task(task, env.db, lambda t, rc: statement_import_body(t, rc, env.drive, env.cfg, env.db, NOW), NOW)
    return next(r for r in store.runs(tid) if r.id == run_id).result


def statements(db):
    return [p for p in db.list_pending() if p.kind == "statement"]


def test_shadow_mode_only_queues_cards(env):
    env.drive.files["d1"] = ("Statement.pdf", env.good)
    out = run_once(env, "shadow")
    assert out["queued"] == 1 and out["imported"] == 0 and env.store.transactions() == []
    assert len(statements(env.db)) == 1


def test_direct_mode_imports_clean_statement_and_queues_bad_one(env):
    env.drive.files.update({"d1": ("good.pdf", env.good), "d2": ("bad.pdf", env.bad)})
    out = run_once(env, "direct")
    assert out["imported"] == 1 and out["queued"] == 1
    assert len(env.store.transactions()) == 2
    assert all(t.user_id == env.cfg.user_id for t in env.store.transactions())


def test_rerun_after_crash_adds_nothing(env):
    env.drive.files["d1"] = ("good.pdf", env.good)
    run_once(env, "direct")
    env.db.set_state("drive_seen", "[]")  # the old seen list is lost in a crash
    out = run_once(env, "direct")
    assert out["imported"] == 0 and out["queued"] == 0 and len(env.store.transactions()) == 2


def test_download_error_is_retried_next_run(env):
    env.drive.files["d1"] = ("good.pdf", env.good)

    def broken(file_id, dest):
        raise OSError("network")

    real = env.drive.download
    env.drive.download = broken
    out = run_once(env, "shadow")
    assert out["queued"] == 0 and "will retry" in out["skipped"][0]
    env.drive.download = real
    assert run_once(env, "shadow")["queued"] == 1


def test_builtin_task_id_and_trigger():
    assert to_apscheduler({"type": "folder", "source": "drive", "minutes": 180}) == {"trigger": "interval", "minutes": 180}
    assert to_apscheduler({"type": "cron", "hour": 7, "minute": 0, "day_of_week": "mon"}) == {
        "trigger": "cron", "hour": 7, "minute": 0, "day_of_week": "mon"}


def test_ensure_builtin_is_idempotent(env):
    store = TaskStore(env.db)
    ensure_builtin_tasks(store, NOW)
    ensure_builtin_tasks(store, NOW)
    assert [t.id for t in store.all()] == [f"{env.cfg.user_id}:statement_import"]


def test_scheduler_follows_task_changes(env):
    from apscheduler.schedulers.background import BackgroundScheduler

    from server.loops.triggers import LoopScheduler

    cfg = env.cfg.model_copy(update={"flags": {"loops": True}})
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        loops = LoopScheduler(sched, cfg, lambda user, tid: None)
        store = TaskStore(Db(cfg.db_path, cfg.user_id))
        ensure_builtin_tasks(store, NOW)
        loops.sync(cfg.user_id)
        assert [j.id for j in sched.get_jobs()] == [f"loop:{cfg.user_id}:{cfg.user_id}:statement_import"]
        store.set_status(f"{cfg.user_id}:statement_import", "paused")
        loops.sync(cfg.user_id)
        assert sched.get_jobs() == []
    finally:
        sched.shutdown(wait=False)


def test_server_schedules_builtin_task_for_new_account(tmp_path):
    import shutil

    from fastapi.testclient import TestClient

    from server.agent.adapters import FakeAdapter
    from server.api.app import create_app
    from tests.api.test_auth import PW
    from tests.conftest import FIXTURE, git

    root = tmp_path / "data"
    shutil.copytree(FIXTURE, root)
    (root / "memory" / "core.yaml").rename(root / "memory.yaml")
    shutil.rmtree(root / "memory")
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.test"),
                 ("config", "user.name", "T"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        git(root, *args)
    from server.config import Config

    cfg = Config(data_repo=root, flags={"loops": True})
    with TestClient(create_app(cfg, lambda: FakeAdapter([]), start_scheduler=True), base_url="http://localhost") as c:
        c.post("/api/auth/setup", json={"username": "avery", "password": PW})
        jobs = [j.id for j in c.app.state.loops.scheduler.get_jobs()]
    assert "loop:avery:avery:statement_import" in jobs


def test_bad_cron_is_refused_and_never_breaks_the_scheduler(env):
    from apscheduler.schedulers.background import BackgroundScheduler
    from pydantic import ValidationError

    from server.loops.tasks import ScheduledTask
    from server.loops.triggers import LoopScheduler
    from server.toolkits.core.schedule import ScheduleTaskArgs

    for bad in ({"type": "cron", "hour": 25, "minute": 0}, {"type": "cron", "hour": 8, "day_of_week": "funday"}):
        with pytest.raises(ValidationError):
            ScheduleTaskArgs(name="n", brief="check things", trigger=bad)
    cfg = env.cfg.model_copy(update={"flags": {"loops": True}})
    store = TaskStore(Db(cfg.db_path, cfg.user_id))
    store.add(ScheduledTask(name="old", kind="agent", trigger={"type": "cron", "hour": 25}, created_by="ui"), NOW)
    ensure_builtin_tasks(store, NOW)
    sched = BackgroundScheduler()
    sched.start(paused=True)
    try:
        LoopScheduler(sched, cfg, lambda u, t: None).sync(cfg.user_id)  # must not raise
        assert len(sched.get_jobs()) == 1  # the good one still scheduled
    finally:
        sched.shutdown(wait=False)


def test_crash_before_the_card_leaves_the_file_for_next_run(env, monkeypatch):
    env.drive.files["d1"] = ("good.pdf", env.good)
    real = env.db.add_pending
    calls = []

    def boom(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("crash")
        return real(*a, **k)

    monkeypatch.setattr(env.db, "add_pending", boom)
    run_once(env, "shadow")  # failed run: the alert itself goes through the real add_pending
    monkeypatch.setattr(env.db, "add_pending", real)
    assert run_once(env, "shadow")["queued"] == 1
    assert run_once(env, "shadow")["queued"] == 0


def test_without_google_the_import_loop_waits_quietly(env):
    from server.loops.service import execute

    cfg = env.cfg.model_copy(update={"flags": {"loops": True, "google": False}})
    store = TaskStore(Db(cfg.db_path, cfg.user_id))
    ensure_builtin_tasks(store, NOW)
    tid = f"{cfg.user_id}:statement_import"
    for _ in range(2):
        execute(cfg, cfg.user_id, tid, lambda: None)
    run = store.runs(tid, 1)[0]
    assert run.status == "ok" and "Google" in run.result["skipped"][0]
    assert [p for p in Db(cfg.db_path, cfg.user_id).list_pending() if p.kind == "alert"] == []


def test_repeated_failures_raise_one_alert_until_dismissed(env):
    store = TaskStore(env.db)
    ensure_builtin_tasks(store, NOW)
    task = store.get(f"{env.cfg.user_id}:statement_import")

    def boom(t, rc):
        raise RuntimeError("x")

    run_task(task, env.db, boom, NOW)
    run_task(task, env.db, boom, NOW)
    alerts = [p for p in env.db.list_pending() if p.kind == "alert"]
    assert len(alerts) == 1
    env.db.set_pending_status(alerts[0].id, "rejected")
    run_task(task, env.db, boom, NOW)
    assert len([p for p in env.db.list_pending() if p.kind == "alert"]) == 1
