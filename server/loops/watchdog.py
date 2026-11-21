"""Dead man's switch: alert when a task misses its check-in or a pending item waits too long."""

from datetime import datetime, timedelta

from server.store.db import Db

from .runner import paused
from .tasks import TaskStore
from .triggers import interval_minutes

WAITING_TOO_LONG = timedelta(days=3)
CRON_GRACE = timedelta(hours=2)  # a daily task may run a little late before it counts as missed


def _due(trigger: dict) -> timedelta:
    minutes = interval_minutes(trigger)
    if trigger.get("type") == "cron":
        return timedelta(minutes=minutes) + CRON_GRACE
    return timedelta(minutes=2 * minutes)


def _raise(db: Db, key: str, title: str, detail: str, now: datetime) -> bool:
    if db.pending_exists("alert", key):  # waiting, or dismissed before: never raise twice
        return False
    db.add_pending("alert", {"title": title, "detail": detail, "key": key}, "watchdog", now, key)
    return True


def check(db: Db, store: TaskStore, now: datetime) -> list[str]:
    raised = []
    if not paused(db):
        for t in store.all():
            if t.status != "active":
                continue
            last = datetime.fromisoformat(t.last_checkin or t.created_at)
            if now - last > _due(t.trigger):
                key = f"stale:{t.id}"
                if _raise(
                    db, key, f"{t.name} missed its run", f"last check-in {last:%Y-%m-%d %H:%M}", now
                ):
                    raised.append(key)
    for p in db.list_pending():
        if p.kind == "alert":
            continue
        if now - datetime.fromisoformat(p.created_at) > WAITING_TOO_LONG:
            key = f"waiting:{p.id}"
            if _raise(db, key, "A card is waiting for you", f"pending item {p.id} ({p.kind})", now):
                raised.append(key)
    return raised
