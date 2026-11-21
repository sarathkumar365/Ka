"""Scheduled tasks for the loops screen: list, create, pause, delete, run now, the stop switch."""

import threading
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from server.config import Config
from server.flags import require_flag
from server.loops import triggers
from server.loops.runner import PAUSED
from server.loops.tasks import ScheduledTask, TaskStore
from server.store.db import Db
from server.toolkits.core.schedule import ScheduleTaskArgs

from .deps import get_cfg, get_db, get_user

router = APIRouter(dependencies=[Depends(require_flag("loops"))])
MAX_ACTIVE = 10  # agent loops per account; built-ins do not count


class TaskPatch(BaseModel):
    status: Literal["active", "paused"] | None = None
    mode: Literal["shadow", "direct"] | None = None


class PausedBody(BaseModel):
    paused: bool


class NewTask(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    brief: str = Field(min_length=5, max_length=2000)
    trigger: dict
    toolkits: list[str] = []


def _counts(db: Db, task_id: str) -> dict[str, int]:
    rows = db.conn.execute(
        "select status, count(*) from pending where user_id=? and kind in ('tool_write', 'statement')"
        " and json_extract(payload, '$.task_id') = ? group by status",
        (db.user_id, task_id),
    ).fetchall()
    by = dict(rows)
    return {"approved": by.get("approved", 0), "rejected": by.get("rejected", 0)}


def _row(db: Db, store: TaskStore, t: ScheduledTask) -> dict:
    last = store.runs(t.id, 1)
    return (
        t.model_dump(mode="json")
        | {"last_run": asdict(last[0]) if last else None}
        | _counts(db, t.id)
    )


def _task(store: TaskStore, task_id: str) -> ScheduledTask:
    t = store.get(task_id)
    if t is None:
        raise HTTPException(404, "no such task")
    return t


@router.get("/loops")
def list_tasks(db: Db = Depends(get_db)):
    store = TaskStore(db)
    return [_row(db, store, t) for t in store.all()]


@router.post("/loops")
def create(
    body: NewTask, db: Db = Depends(get_db), user: str = Depends(get_user),
    cfg: Config = Depends(get_cfg),
):  # fmt: skip
    from server.toolkits.base import available

    try:
        args = ScheduleTaskArgs(**body.model_dump())
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"]) from None
    unknown = [k for k in args.toolkits if k not in {m.name for m in available(cfg)}]
    if unknown:
        raise HTTPException(422, f"unknown toolkits: {', '.join(unknown)}")
    store = TaskStore(db)
    active = [t for t in store.all() if t.kind == "agent" and t.status == "active"]
    if len(active) >= MAX_ACTIVE:
        raise HTTPException(409, f"You have {MAX_ACTIVE} active loops. Pause one first.")
    task = ScheduledTask(
        name=args.name, kind="agent", trigger=args.trigger, brief=args.brief,
        toolkits=args.toolkits, created_by="ui",
    )  # fmt: skip
    tid = store.add(task, datetime.now())
    triggers.notify(user)
    return _row(db, store, store.get(tid))


@router.patch("/loops/{task_id}")
def update(task_id: str, body: TaskPatch, db: Db = Depends(get_db), user: str = Depends(get_user)):
    store = TaskStore(db)
    _task(store, task_id)
    if body.status:
        store.set_status(task_id, body.status)
    if body.mode:
        store.set_mode(task_id, body.mode)
    triggers.notify(user)
    return _row(db, store, store.get(task_id))


@router.delete("/loops/{task_id}")
def delete(task_id: str, db: Db = Depends(get_db), user: str = Depends(get_user)):
    store = TaskStore(db)
    if _task(store, task_id).kind == "builtin":
        raise HTTPException(409, "built-in tasks can be paused, not deleted")
    store.delete(task_id)
    triggers.notify(user)
    return {"ok": True}


@router.get("/loops/{task_id}/runs")
def runs(task_id: str, db: Db = Depends(get_db)):
    store = TaskStore(db)
    _task(store, task_id)
    return [asdict(r) for r in store.runs(task_id)]


@router.post("/loops/{task_id}/run")
def run_now(
    task_id: str, request: Request, db: Db = Depends(get_db), user: str = Depends(get_user),
    _cfg: Config = Depends(get_cfg),
):  # fmt: skip
    from server.loops.service import LoopBusy, busy, execute, running_task

    _task(TaskStore(db), task_id)
    if busy(user):  # one run at a time per account
        if running_task(user) in (task_id, None):
            raise HTTPException(409, "This loop is already running.")
        raise HTTPException(409, "Another loop is running. Try again when it finishes.")
    state = request.app.state

    def run() -> None:  # a run takes up to 5 minutes: it must not hold a request thread
        try:
            execute(state.cfg, user, task_id, state.adapter_factory, state.private_factory)
        except LoopBusy:
            pass  # another run of this account started first; that one counts

    threading.Thread(target=run, daemon=True, name=f"loop-{task_id}").start()
    return JSONResponse({"started": True}, status_code=202)


@router.put("/loops/paused")
def set_paused(body: PausedBody, db: Db = Depends(get_db)):
    db.set_state(PAUSED, "1" if body.paused else "0")
    return {"paused": body.paused}
