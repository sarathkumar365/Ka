"""Scheduled tasks and their run log in SQLite, scoped to one user."""

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from server.integrations.data_repo.schemas.common import KaModel
from server.store.db import Db


class RunLimits(KaModel):
    seconds: int = Field(default=300, ge=1)
    model_calls: int = Field(default=20, ge=0)
    tool_calls: int = Field(default=30, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0.50"), ge=0)


class ScheduledTask(KaModel):
    id: str = ""
    user_id: str = ""
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["builtin", "agent"]
    builtin: str | None = None
    trigger: dict
    brief: str = ""
    toolkits: list[str] = []
    checks: list[str] = []
    limits: RunLimits = RunLimits()
    mode: Literal["shadow", "direct"] = "shadow"
    status: Literal["active", "paused"] = "active"
    created_by: Literal["code", "ui", "ka"]
    created_at: str = ""
    last_checkin: str | None = None


@dataclass
class RunCounts:
    model_calls: int = 0
    tool_calls: int = 0
    cost_usd: Decimal = Decimal(0)


@dataclass
class TaskRun:
    id: int
    task_id: str
    started_at: str
    finished_at: str | None
    status: str
    reason: str
    model_calls: int
    tool_calls: int
    cost_usd: str
    result: dict = field(default_factory=dict)


COLS = (
    "id, user_id, name, kind, builtin, trigger, brief, toolkits, checks, limits, mode, status,"
    " created_by, created_at, last_checkin"
)


class TaskStore:
    def __init__(self, db: Db) -> None:
        self.db, self.conn, self.user = db, db.conn, db.user_id

    def _row(self, r) -> ScheduledTask:
        keys = [c.strip() for c in COLS.split(",")]
        d = dict(zip(keys, r, strict=True))
        for k in ("trigger", "toolkits", "checks", "limits"):
            d[k] = json.loads(d[k])
        return ScheduledTask(**d)

    def add(self, task: ScheduledTask, now: datetime, task_id: str | None = None) -> str:
        tid = task_id or f"T-{now:%Y%m%d}-{secrets.token_hex(2)}"
        with self.conn:
            self.conn.execute(
                f"insert into scheduled_tasks ({COLS}) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    tid, self.user, task.name, task.kind, task.builtin, json.dumps(task.trigger),
                    task.brief, json.dumps(task.toolkits), json.dumps(task.checks),
                    task.limits.model_dump_json(), task.mode, task.status, task.created_by,
                    now.isoformat(), None,
                ),
            )  # fmt: skip
        return tid

    def get(self, task_id: str) -> ScheduledTask | None:
        r = self.conn.execute(
            f"select {COLS} from scheduled_tasks where id=? and user_id=?", (task_id, self.user)
        ).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[ScheduledTask]:
        rows = self.conn.execute(
            f"select {COLS} from scheduled_tasks where user_id=? order by created_at", (self.user,)
        ).fetchall()
        return [self._row(r) for r in rows]

    def _set(self, task_id: str, column: str, value) -> None:
        with self.conn:
            self.conn.execute(
                f"update scheduled_tasks set {column}=? where id=? and user_id=?",
                (value, task_id, self.user),
            )

    def set_status(self, task_id: str, status: Literal["active", "paused"]) -> None:
        self._set(task_id, "status", status)

    def set_mode(self, task_id: str, mode: Literal["shadow", "direct"]) -> None:
        self._set(task_id, "mode", mode)

    def checkin(self, task_id: str, now: datetime) -> None:
        self._set(task_id, "last_checkin", now.isoformat())

    def delete(self, task_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "delete from scheduled_tasks where id=? and user_id=?", (task_id, self.user)
            )

    def start_run(self, task_id: str, now: datetime, status: str = "running") -> int:
        with self.conn:
            cur = self.conn.execute(
                "insert into task_runs (task_id, user_id, started_at, status) values (?,?,?,?)",
                (task_id, self.user, now.isoformat(), status),
            )
        return cur.lastrowid

    def finish_run(
        self, run_id: int, status: str, reason: str, counts: RunCounts, result: dict, now: datetime
    ) -> None:
        with self.conn:
            self.conn.execute(
                "update task_runs set finished_at=?, status=?, reason=?, model_calls=?,"
                " tool_calls=?, cost_usd=?, result=? where id=? and user_id=?",
                (
                    now.isoformat(), status, reason, counts.model_calls, counts.tool_calls,
                    str(counts.cost_usd), json.dumps(result, default=str), run_id, self.user,
                ),
            )  # fmt: skip

    def runs(self, task_id: str, limit: int = 20) -> list[TaskRun]:
        rows = self.conn.execute(
            "select id, task_id, started_at, finished_at, status, reason, model_calls, tool_calls,"
            " cost_usd, result from task_runs where task_id=? and user_id=?"
            " order by id desc limit ?",
            (task_id, self.user, limit),
        ).fetchall()
        return [TaskRun(*r[:9], json.loads(r[9])) for r in rows]

    def write_claimed(self, task_id: str, key: str) -> bool:
        row = self.conn.execute(
            "select 1 from task_writes where task_id=? and write_key=? and user_id=?",
            (task_id, key, self.user),
        ).fetchone()
        return row is not None

    def claim_write(self, task_id: str, key: str, run_id: int, now: datetime) -> bool:
        """True the first time a write key is seen; a retried run gets False and skips it."""
        with self.conn:
            cur = self.conn.execute(
                "insert or ignore into task_writes (task_id, write_key, run_id, at, user_id)"
                " values (?,?,?,?,?)",
                (task_id, key, run_id, now.isoformat(), self.user),
            )
        return cur.rowcount == 1
