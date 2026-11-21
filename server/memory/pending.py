"""Pending memory queue: inferred facts wait here until the owner approves them."""

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from server.integrations.data_repo.loader import KaData, load_data
from server.integrations.data_repo.writer import ChangeError, Patch, apply_change, plan_change
from server.store.db import Db

KIND = "memory"


class PendingError(Exception):
    """Message is safe to show the owner or the model."""


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def queue_memory(
    db: Db,
    data: KaData,
    text: str,
    type: Literal["fact", "preference", "rule"],
    replaces: str | None,
    source: str | None,
    now: datetime,
    toolkit: str = "core",
) -> dict:
    key = _key(text)
    mem = data.memory if toolkit == "core" else data.toolkit_memory.get(toolkit)
    if mem is None:
        raise PendingError(f"no memory file for {toolkit}")
    active = {e.id: e for e in mem.entries if e.status == "active"}
    if key in {_key(e.text) for e in active.values()} or db.pending_exists(KIND, key):
        return {"queued": False, "reason": "duplicate"}
    if replaces is not None and replaces not in active:
        raise PendingError(f"cannot replace {replaces}: not an active memory")
    payload = {"type": type, "text": text.strip(), "replaces": replaces, "toolkit": toolkit}
    return {"queued": True, "pending_id": db.add_pending(KIND, payload, source, now, key)}


def approve_pending(item_id: int, root: Path, db: Db, today: date) -> str:
    item = db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != KIND:
        raise PendingError(f"no pending memory item {item_id}")
    p = item.payload
    scope = p.get("toolkit", "core")
    data = load_data(root)
    mem = data.memory if scope == "core" else data.toolkit_memory.get(scope)
    if mem is None:
        raise PendingError(f"no memory file for {scope}")
    active = {e.id: e for e in mem.entries if e.status == "active"}
    if _key(p["text"]) in {_key(e.text) for e in active.values()}:
        raise PendingError("already in memory; reject this item")
    if p.get("replaces") and p["replaces"] not in active:
        raise PendingError(f"{p['replaces']} is no longer active; reject or re-queue this item")
    fields = {
        "type": p["type"],
        "text": p["text"],
        "created": today.isoformat(),
        "updated": today.isoformat(),
        "status": "active",
    }
    if item.source:
        fields["source"] = item.source
    try:
        plan = plan_change(root, Patch(target="memory", op="add", scope=scope, fields=fields))
        commit = apply_change(root, plan)
    except ChangeError as e:
        raise PendingError(str(e)) from e
    db.set_pending_status(item_id, "approved")  # the new entry exists now; do not queue it twice
    result = f"added {plan.key} ({commit})"
    if p.get("replaces"):
        retire = Patch(
            target="memory",
            scope=scope,
            op="update",
            key=p["replaces"],
            fields={"status": "retired", "replaced_by": plan.key, "updated": today.isoformat()},
        )
        try:
            result += f"; retired {p['replaces']} ({apply_change(root, plan_change(root, retire))})"
        except ChangeError as e:
            raise PendingError(f"{result}, but could not retire {p['replaces']}: {e}") from e
    return result


def reject_pending(item_id: int, db: Db) -> None:
    item = db.get_pending(item_id)
    if item is None or item.status != "pending":
        raise PendingError(f"no pending item {item_id}")
    db.set_pending_status(item_id, "rejected")


TOOL_WRITE = "tool_write"
ALERT = "alert"


def queue_tool_write(
    db: Db,
    tool: str,
    args: dict,
    summary: str,
    diff: str,
    run_id: int | None,
    now: datetime,
    after_untrusted: bool = False,
    task_id: str | None = None,
) -> int:
    """A write a loop wanted to make, waiting for the owner (shadow mode)."""
    payload = {
        "tool": tool, "args": args, "summary": summary, "diff": diff, "run_id": run_id,
        "after_untrusted": after_untrusted, "task_id": task_id,
    }  # fmt: skip
    return db.add_pending(TOOL_WRITE, payload, "loop", now)


def approve_tool_write(item_id: int, ctx) -> str:
    """Run the tool again now (the data may have changed) and apply what it proposes."""
    import json

    from server.agent.tools import PendingWrite, ToolError, run_tool

    item = ctx.db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != TOOL_WRITE:
        raise PendingError(f"no pending loop write {item_id}")
    try:
        result = run_tool(item.payload["tool"], item.payload["args"], ctx)
        out = (
            result.apply() if isinstance(result, PendingWrite) else json.dumps(result, default=str)
        )
    except ToolError as e:
        raise PendingError(f"could not apply: {e}") from e
    ctx.db.set_pending_status(item_id, "approved")
    return out


def dismiss(item_id: int, db: Db, kind: str) -> None:
    item = db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != kind:
        raise PendingError(f"no pending {kind} {item_id}")
    db.set_pending_status(item_id, "rejected")
