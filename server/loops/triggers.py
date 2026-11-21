"""Scheduled tasks to APScheduler jobs, kept in sync while the server runs (no restart needed)."""

import logging
from collections.abc import Callable
from datetime import datetime

from server.config import Config
from server.flags import is_on
from server.store.db import Db

from .tasks import ScheduledTask, TaskStore

log = logging.getLogger(__name__)


def to_apscheduler(trigger: dict) -> dict:
    kind = trigger.get("type")
    if kind in ("interval", "folder"):
        return {"trigger": "interval", "minutes": int(trigger["minutes"])}
    if kind == "cron":
        out = {
            "trigger": "cron",
            "hour": int(trigger["hour"]),
            "minute": int(trigger.get("minute", 0)),
        }
        if trigger.get("day_of_week"):
            out["day_of_week"] = trigger["day_of_week"]
        return out
    raise ValueError(f"unknown trigger type: {kind}")


def check_trigger(trigger: dict) -> dict:
    """The APScheduler arguments, after APScheduler itself accepted them (hour 25 fails here)."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    args = to_apscheduler(trigger)
    rest = {k: v for k, v in args.items() if k != "trigger"}
    if args["trigger"] == "cron":
        CronTrigger(**rest)
    else:
        if rest["minutes"] < 1:
            raise ValueError("minutes must be positive")
        IntervalTrigger(**rest)
    return args


def interval_minutes(trigger: dict) -> int:
    """How often a task should check in; cron tasks are daily or weekly at most."""
    if trigger.get("type") in ("interval", "folder"):
        return int(trigger["minutes"])
    return 7 * 24 * 60 if trigger.get("day_of_week") else 24 * 60


class LoopScheduler:
    """Owns one APScheduler job per active task; `sync` after any change to a user's tasks."""

    def __init__(self, scheduler, cfg: Config, run: Callable[[str, str], None]) -> None:
        self.scheduler, self.cfg, self.run = scheduler, cfg, run

    def sync(self, user_id: str) -> None:
        db = Db(self.cfg.db_path, user_id)
        try:
            tasks = TaskStore(db).all() if is_on(self.cfg, "loops") else []
        finally:
            db.conn.close()
        prefix = f"loop:{user_id}:"
        wanted = {f"{prefix}{t.id}": t for t in tasks if t.status == "active"}
        for job in self.scheduler.get_jobs():
            if job.id.startswith(prefix) and job.id not in wanted:
                job.remove()
        for job_id, t in wanted.items():
            self._add(job_id, user_id, t)

    def _add(self, job_id: str, user_id: str, t: ScheduledTask) -> None:
        extra = {}
        if t.builtin:  # built-ins also run once at start, so a missed folder check catches up
            extra["next_run_time"] = datetime.now()
        try:  # one bad stored task must never stop the others or the server from starting
            self.scheduler.add_job(
                self.run, args=(user_id, t.id), id=job_id, replace_existing=True, coalesce=True,
                max_instances=1, misfire_grace_time=None, **check_trigger(t.trigger), **extra,
            )  # fmt: skip
        except Exception:  # noqa: BLE001
            log.warning("task %s has a bad trigger; not scheduled", t.id)


ACTIVE: LoopScheduler | None = None  # set by the server while it runs


def notify(user_id: str) -> None:
    """A user's tasks changed: reschedule them now, if the server's scheduler is running."""
    if ACTIVE is not None:
        ACTIVE.sync(user_id)
