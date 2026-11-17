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
) -> dict:
    key = _key(text)
    active = {e.id: e for e in data.memory.entries if e.status == "active"}
    if key in {_key(e.text) for e in active.values()} or db.pending_exists(KIND, key):
        return {"queued": False, "reason": "duplicate"}
    if replaces is not None and replaces not in active:
        raise PendingError(f"cannot replace {replaces}: not an active memory")
    payload = {"type": type, "text": text.strip(), "replaces": replaces}
    return {"queued": True, "pending_id": db.add_pending(KIND, payload, source, now, key)}


def approve_pending(item_id: int, root: Path, db: Db, today: date) -> str:
    item = db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != KIND:
        raise PendingError(f"no pending memory item {item_id}")
    p = item.payload
    active = {e.id: e for e in load_data(root).memory.entries if e.status == "active"}
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
        plan = plan_change(root, Patch(target="memory", op="add", fields=fields))
        commit = apply_change(root, plan)
    except ChangeError as e:
        raise PendingError(str(e)) from e
    db.set_pending_status(item_id, "approved")  # the new entry exists now; do not queue it twice
    result = f"added {plan.key} ({commit})"
    if p.get("replaces"):
        retire = Patch(
            target="memory",
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
