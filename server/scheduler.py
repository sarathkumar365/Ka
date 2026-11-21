"""Background jobs inside `ka serve`: nightly memory extraction, with catch-up for missed days."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from server.agent.adapters import Adapter
from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.memory.extract import extract_memories
from server.store.db import Db

log = logging.getLogger(__name__)

LAST_DAY = "last_extraction_day"
MAX_CATCH_UP = 7


@dataclass
class ScheduledJob:
    id: str
    trigger: dict  # keyword arguments for BackgroundScheduler.add_job, e.g. {"trigger": "cron"}
    run: Callable[[], None]


def start_scheduler(jobs: list[ScheduledJob]) -> BackgroundScheduler:
    # Loops get their own workers, so busy loops never hold up imports, extraction or the watchdog.
    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(10), "loops": ThreadPoolExecutor(4)}
    )
    for job in jobs:
        # coalesce plus no grace limit: a run missed while the laptop slept happens once on wake
        scheduler.add_job(
            job.run,
            id=job.id,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=None,
            **job.trigger,
        )
    scheduler.start()
    return scheduler


def catch_up_extraction(
    cfg: Config,
    db: Db,
    adapter_factory: Callable[[], Adapter],
    today: date,
    extract=None,
    private_factory: Callable[[], Adapter] | None = None,
) -> list[date]:
    """Extract every day from the last one done up to yesterday, at most MAX_CATCH_UP days."""
    last = db.get_state(LAST_DAY)
    yesterday = today - timedelta(days=1)
    start = date.fromisoformat(last) + timedelta(days=1) if last else yesterday
    start = max(start, today - timedelta(days=MAX_CATCH_UP))
    days = [start + timedelta(days=n) for n in range((yesterday - start).days + 1)]
    if not days:
        return []
    extract = extract or extract_memories
    adapter = adapter_factory()
    private = private_factory() if private_factory else None
    data = load_data(cfg.data_repo)
    for day in days:
        extract(day, db, data, adapter, datetime.now(), private_adapter=private)
        db.set_state(LAST_DAY, day.isoformat())
    return days


def nightly_job(
    cfg: Config,
    adapter_factory: Callable[[], Adapter],
    today: Callable[[], date] | None = None,
    private_factory: Callable[[], Adapter] | None = None,
) -> ScheduledJob:
    busy = threading.Lock()  # the start-up catch-up and the 03:00 run share it

    def run() -> None:
        if not busy.acquire(blocking=False):
            return  # the other run is extracting the same days
        db = None
        try:
            db = Db(cfg.db_path, cfg.user_id)
            from server import users

            # Messages are stamped in server time, so a day is only over once it is over both
            # for the account and for the server.
            day = today() if today else min(users.local_today(cfg), date.today())
            days = catch_up_extraction(
                cfg, db, adapter_factory, day, private_factory=private_factory
            )
            if days:
                db.add_activity("extraction", f"extracted {len(days)} day(s)", datetime.now())
        except Exception as e:  # a background job must never take the server down
            log.exception("nightly extraction failed")
            reason = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
            if db is not None:
                db.add_activity("extraction", f"extraction failed: {reason}", datetime.now())
        finally:
            if db is not None:
                db.conn.close()
            busy.release()

    # hourly, as the server runs it per account: each run catches up to the local yesterday
    return ScheduledJob("nightly_extraction", {"trigger": "interval", "hours": 1}, run)
