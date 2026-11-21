from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from server.agent.adapters import FakeAdapter, Reply
from server.agent.adapters.base import Usage
from server.loops.runner import Budget, BudgetAdapter, LimitHit, run_task
from server.loops.tasks import RunLimits, ScheduledTask, TaskStore
from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0)


@pytest.fixture
def db():
    return Db(":memory:", "avery")


def make_task(store, **kw) -> ScheduledTask:
    base = {"name": "test", "kind": "agent", "trigger": {"type": "interval", "minutes": 60},
            "brief": "do it", "created_by": "code"}
    tid = store.add(ScheduledTask(**{**base, **kw}), NOW)
    return store.get(tid)


def test_task_round_trip_and_scoped_to_user(db):
    s = TaskStore(db)
    t = make_task(s, limits=RunLimits(tool_calls=2))
    assert t.id.startswith("T-20310405-") and t.mode == "shadow" and t.limits.tool_calls == 2
    other = Db(":memory:", "blake")
    other.conn = db.conn
    assert TaskStore(other).all() == []


def test_tool_limit_stops_run_and_alerts(db):
    s = TaskStore(db)
    task = make_task(s, limits=RunLimits(tool_calls=2))

    def body(t, rc):
        for _ in range(3):
            rc.budget.charge_tool()

    run_task(task, db, body, NOW)
    r = s.runs(task.id)[0]
    assert r.status == "stopped" and "tool_calls" in r.reason and r.tool_calls == 3
    assert [p.kind for p in db.list_pending()] == ["alert"]
    assert s.get(task.id).last_checkin == NOW.isoformat()


def test_paused_switch_skips(db):
    s = TaskStore(db)
    task = make_task(s)
    db.set_state("loops_paused", "1")
    ran = []
    run_task(task, db, lambda t, rc: ran.append(1), NOW)
    assert s.runs(task.id)[0].status == "skipped" and ran == []


def test_paused_task_skips(db):
    s = TaskStore(db)
    task = make_task(s)
    s.set_status(task.id, "paused")
    run_task(s.get(task.id), db, lambda t, rc: {}, NOW)
    assert s.runs(task.id)[0].status == "skipped"


def test_failure_is_recorded_without_details(db):
    s = TaskStore(db)
    task = make_task(s)

    def body(t, rc):
        raise RuntimeError("secret path /Users/x")

    run_task(task, db, body, NOW)
    r = s.runs(task.id)[0]
    assert r.status == "failed" and r.reason == "RuntimeError" and len(db.list_pending()) == 1


def test_write_key_claimed_once(db):
    s = TaskStore(db)
    assert s.claim_write("T-1", "drive:abc", 1, NOW) and not s.claim_write("T-1", "drive:abc", 2, NOW)


def test_cost_limit_uses_usage():
    budget = Budget(RunLimits(cost_usd=Decimal("0.50")))
    replies = [Reply(text="a", usage=Usage(1, 1, cost_usd=Decimal("0.30")))] * 3
    adapter = BudgetAdapter(FakeAdapter(replies), budget)
    adapter.complete([], [])
    with pytest.raises(LimitHit, match="cost_usd"):
        adapter.complete([], [])
        adapter.complete([], [])


def test_time_limit():
    t = [0.0]
    budget = Budget(RunLimits(seconds=10), clock=lambda: t[0])
    t[0] = 11
    with pytest.raises(LimitHit, match="seconds"):
        budget.check()


def test_ok_run_records_result(db):
    s = TaskStore(db)
    task = make_task(s)
    run_task(task, db, lambda t, rc: {"new": 2}, NOW + timedelta(minutes=1))
    r = s.runs(task.id)[0]
    assert r.status == "ok" and r.result == {"new": 2} and db.list_pending() == []
