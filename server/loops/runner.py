"""One run of a scheduled task: checks the stop switches, enforces hard limits, logs the result."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from server.store.db import Db

from .tasks import RunCounts, RunLimits, ScheduledTask, TaskStore

log = logging.getLogger(__name__)
PAUSED = "loops_paused"


class LimitHit(Exception):
    pass


class Budget:
    def __init__(self, limits: RunLimits, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits, self.clock = limits, clock
        self.started = clock()
        self.counts = RunCounts()

    def check(self) -> None:
        c, lim = self.counts, self.limits
        if self.clock() - self.started > lim.seconds:
            raise LimitHit("seconds limit reached")
        if c.model_calls > lim.model_calls:
            raise LimitHit("model_calls limit reached")
        if c.tool_calls > lim.tool_calls:
            raise LimitHit("tool_calls limit reached")
        if c.cost_usd > lim.cost_usd:
            raise LimitHit("cost_usd limit reached")

    def charge_model(self, usage) -> None:
        self.counts.model_calls += 1
        cost = getattr(usage, "cost_usd", None)
        if cost is not None:
            self.counts.cost_usd += Decimal(cost)
        self.check()

    def charge_tool(self) -> None:
        self.counts.tool_calls += 1
        self.check()


class BudgetAdapter:
    """Counts every model call of a run against its limits."""

    def __init__(self, inner, budget: Budget) -> None:
        self.inner, self.budget = inner, budget
        self.model = getattr(inner, "model", "unknown")

    def complete(self, messages: list[dict], tools: list[dict]):
        self.budget.check()
        reply = self.inner.complete(messages, tools)
        self.budget.charge_model(reply.usage)
        return reply


@dataclass
class RunContext:
    budget: Budget
    store: TaskStore
    run_id: int
    task: ScheduledTask
    queued: list[int] = field(default_factory=list)


def paused(db: Db) -> bool:
    return db.get_state(PAUSED) == "1"


def _alert(
    db: Db, task: ScheduledTask, run_id: int, title: str, detail: str, now: datetime
) -> None:
    """One open alert per task: a task failing every run does not pile up cards."""
    if any(p.kind == "alert" and p.payload.get("task_id") == task.id for p in db.list_pending()):
        return
    payload = {"title": title, "detail": detail, "task_id": task.id, "run_id": run_id}
    db.add_pending("alert", payload, "loop", now, f"run:{run_id}")


def run_task(
    task: ScheduledTask,
    db: Db,
    body: Callable[[ScheduledTask, RunContext], dict | None],
    now: datetime,
    loops_on: bool = True,
) -> int:
    store = TaskStore(db)
    if not loops_on or paused(db) or task.status != "active":
        why = "loops off" if not loops_on else "stop switch on" if paused(db) else "task paused"
        run_id = store.start_run(task.id, now, status="skipped")
        store.finish_run(run_id, "skipped", why, RunCounts(), {}, now)
        return run_id
    run_id = store.start_run(task.id, now)
    budget = Budget(task.limits)
    rc = RunContext(budget, store, run_id, task)
    status, reason, result = "ok", "", {}
    try:
        result = body(task, rc) or {}
        budget.check()
    except LimitHit as e:
        status, reason = "stopped", str(e)
        _alert(db, task, run_id, f"{task.name} stopped", f"{e}; nothing more was done", now)
    except Exception as e:
        log.exception("task %s failed", task.id)
        status, reason = "failed", type(e).__name__
        _alert(db, task, run_id, f"{task.name} failed", f"the run failed ({reason})", now)
    store.finish_run(run_id, status, reason, budget.counts, result, now)
    store.checkin(task.id, now)
    return run_id
