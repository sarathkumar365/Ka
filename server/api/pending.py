from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.memory.pending import PendingError, approve_pending, reject_pending
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()


def _memory_item(db: Db, item_id: int):
    item = db.get_pending(item_id)
    if item is None or item.kind != "memory":
        raise HTTPException(409, f"no pending memory item {item_id}")
    return item


@router.get("/pending")
def list_pending(cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)):
    items = [i for i in db.list_pending() if i.kind == "memory"]
    old: dict[str, str] = {}
    if any(i.payload.get("replaces") for i in items):  # only then is the old text needed
        old = {e.id: e.text for e in load_data(cfg.data_repo).memory.entries}
    return [
        {
            "id": i.id,
            "type": i.payload["type"],
            "text": i.payload["text"],
            "old": old.get(i.payload.get("replaces") or ""),
            "source": i.source,
            "created_at": i.created_at,
        }
        for i in items
    ]


@router.post("/pending/{item_id}/approve")
def approve(
    item_id: int, request: Request, cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)
):
    item = _memory_item(db, item_id)
    try:
        with request.app.state.pending_lock:  # check, commit and status update must not interleave
            result = approve_pending(item_id, cfg.data_repo, db, date.today())
    except PendingError as e:
        raise HTTPException(409, str(e)) from e
    text = item.payload["text"]
    db.add_activity("pending", f"Saved a memory: {text}. You approved it.", datetime.now())
    return {"result": result}


@router.post("/pending/{item_id}/reject")
def reject(item_id: int, db: Db = Depends(get_db)):
    item = _memory_item(db, item_id)
    try:
        reject_pending(item_id, db)
    except PendingError as e:
        raise HTTPException(409, str(e)) from e
    text = item.payload["text"]
    db.add_activity("pending", f"Did not save: {text}. You rejected it.", datetime.now())
    return {}
