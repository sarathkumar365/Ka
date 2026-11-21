from datetime import datetime, timedelta

from server.loops.tasks import ScheduledTask, TaskStore
from server.loops.watchdog import check
from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0)


def test_missed_run_raises_one_alert():
    db = Db(":memory:", "avery")
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60}, created_by="ui"), NOW)
    s.checkin(tid, NOW)
    assert check(db, s, NOW + timedelta(minutes=90)) == []
    assert check(db, s, NOW + timedelta(hours=3)) == [f"stale:{tid}"]
    assert check(db, s, NOW + timedelta(hours=4)) == []  # deduplicated
    alert = db.list_pending()[0]
    assert alert.kind == "alert" and "t" in alert.payload["title"]


def test_never_run_task_counts_from_creation():
    db = Db(":memory:", "avery")
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "cron", "hour": 7}, created_by="ui"), NOW)
    assert check(db, s, NOW + timedelta(hours=25)) == []
    assert check(db, s, NOW + timedelta(hours=27)) == [f"stale:{tid}"]


def test_paused_tasks_and_pause_switch_are_quiet():
    db = Db(":memory:", "avery")
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60}, created_by="ui"), NOW)
    s.set_status(tid, "paused")
    assert check(db, s, NOW + timedelta(days=2)) == []


def test_old_pending_item_raises_alert():
    db = Db(":memory:", "avery")
    item = db.add_pending("memory", {"type": "fact", "text": "x"}, None, NOW, "x")
    assert check(db, TaskStore(db), NOW + timedelta(days=4)) == [f"waiting:{item}"]
    assert check(db, TaskStore(db), NOW + timedelta(days=5)) == []
