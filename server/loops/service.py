"""What a scheduled job does when it fires: load the task, pick its body, run it within limits."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from server.config import Config
from server.flags import is_on
from server.store.db import Db
from server.users import user_config

from .builtin import STATEMENT_IMPORT, statement_import_body
from .runner import run_task
from .tasks import TaskStore
from .watchdog import check

log = logging.getLogger(__name__)
SCHEDULED_WAIT = 360.0  # seconds: longer than one run's 300 s limit


class LoopBusy(Exception):
    """This account already has a loop run going; runs never overlap within one account."""


_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(user_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(user_id, threading.Lock())


_running: dict[str, str] = {}  # user id -> the task now running


def busy(user_id: str) -> bool:
    return _lock(user_id).locked()


def running_task(user_id: str) -> str | None:
    return _running.get(user_id)


def execute(
    cfg: Config, user_id: str, task_id: str, adapter_factory: Callable,
    private_factory: Callable | None = None, wait: float = 0,
) -> int | None:
    """One run at a time per account, so one account's loops cannot fill the shared workers.
    `wait` seconds: queue behind a running one instead of refusing (scheduled runs)."""
    lock = _lock(user_id)
    if not (lock.acquire(timeout=wait) if wait > 0 else lock.acquire(blocking=False)):
        raise LoopBusy(user_id)
    _running[user_id] = task_id
    try:
        return _run(cfg, user_id, task_id, adapter_factory, private_factory)
    finally:
        _running.pop(user_id, None)
        lock.release()


def scheduled(
    cfg: Config, user_id: str, task_id: str, adapter_factory: Callable,
    private_factory: Callable | None = None,
) -> None:
    """The scheduler's entry: two loops due at the same minute run one after the other. Only a run
    still waiting after a whole run's time limit (and some) is skipped until its next tick."""
    try:
        execute(cfg, user_id, task_id, adapter_factory, private_factory, wait=SCHEDULED_WAIT)
    except LoopBusy:
        log.warning("loop %s skipped: another run of this account took too long", task_id)


def _run(
    cfg: Config, user_id: str, task_id: str, adapter_factory: Callable,
    private_factory: Callable | None = None,
) -> int | None:
    ucfg = user_config(cfg, user_id)
    db = Db(ucfg.db_path, user_id)
    try:
        task = TaskStore(db).get(task_id)
        if task is None:
            return None
        now = datetime.now()
        if task.kind == "builtin" and task.builtin == STATEMENT_IMPORT:

            def body(t, rc):
                from server.integrations.google.drive import ApiDrive
                from server.integrations.google.oauth import DRIVE_MISSING, auth_for

                g = ucfg.google
                if not is_on(cfg, "google") or g is None:
                    return {"new": 0, "imported": 0, "queued": 0,
                            "skipped": ["Google Drive not connected; nothing to check"]}  # fmt: skip
                if not g.drive_folder_id:
                    return {"new": 0, "imported": 0, "queued": 0, "skipped": [DRIVE_MISSING]}
                drive = ApiDrive(auth_for(ucfg).credentials())
                return statement_import_body(t, rc, drive, ucfg, db, now)

        else:

            def body(t, rc):
                from server.agent.tools import ToolContext
                from server.finance.store import CsvFinanceStore

                from .agent_task import agent_task_body

                ctx = ToolContext(
                    config=ucfg, store=CsvFinanceStore(ucfg.finance_dir, user_id), db=db
                )
                private = private_factory() if private_factory and is_on(cfg, "private_routing") else None
                return agent_task_body(t, rc, ctx, adapter_factory(), now, private_adapter=private)

        run_id = run_task(task, db, body, now, loops_on=is_on(cfg, "loops"), prices=cfg.prices)
        run = next(r for r in TaskStore(db).runs(task_id, 1))
        db.add_activity(
            "loop", f"{task.name}: {run.status}" + (f" ({run.reason})" if run.reason else ""), now
        )
        return run_id
    finally:
        db.conn.close()


def watchdog(cfg: Config, user_id: str) -> list[str]:
    db = Db(cfg.db_path, user_id)
    try:
        return check(db, TaskStore(db), datetime.now())
    finally:
        db.conn.close()
