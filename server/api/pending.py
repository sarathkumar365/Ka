from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.config import Config
from server.finance.drive_inbox import approve_statement, refresh_imported, reject_statement
from server.finance.sheet_copy import push_from_config
from server.finance.store import CsvFinanceStore
from server.intake.approve import approve_bundle, reject_bundle
from server.integrations.data_repo.loader import load_data
from server.memory.pending import PendingError, approve_pending, reject_pending
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()


class ApproveBody(BaseModel):
    selected: list[str] | None = None


def _item(db: Db, item_id: int):
    item = db.get_pending(item_id)
    if item is None or item.kind not in ("memory", "bundle", "statement"):
        raise HTTPException(409, f"no pending item {item_id}")
    return item


def _bundle_row(db: Db, i) -> dict:
    p = i.payload
    ready = all(
        (o := db.get_pending(n)) is None or o.status != "pending" for n in p.get("needs", [])
    )
    return {
        "id": i.id,
        "kind": "bundle",
        "title": p["title"],
        "section": p["section"],
        "blocked": p.get("blocked"),
        "note": p.get("note"),
        "needs": p.get("needs", []),
        "ready": ready,
        "items": [{k: it[k] for k in ("id", "label", "detail", "selected")} for it in p["items"]],
        "source": i.source,
        "created_at": i.created_at,
    }


@router.get("/pending")
def list_pending(cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)):
    items = db.list_pending()
    memory = [i for i in items if i.kind == "memory"]
    old: dict[str, str] = {}
    if any(i.payload.get("replaces") for i in memory):  # only then is the old text needed
        old = {e.id: e.text for e in load_data(cfg.data_repo).memory.entries}
    rows: list[dict] = [
        {
            "id": i.id,
            "kind": "memory",
            "type": i.payload["type"],
            "text": i.payload["text"],
            "old": old.get(i.payload.get("replaces") or ""),
            "source": i.source,
            "created_at": i.created_at,
        }
        for i in memory
    ]
    rows += [_bundle_row(db, i) for i in items if i.kind == "bundle"]
    statements = [
        {"id": i.id, "kind": "statement", **{k: v for k, v in i.payload.items() if k != "path"}}
        | {"source": i.source, "created_at": i.created_at}
        for i in items
        if i.kind == "statement"
    ]
    if statements:
        rows += refresh_imported(statements, CsvFinanceStore(cfg.finance_dir))
    return sorted(rows, key=lambda r: r["id"])


@router.post("/pending/{item_id}/approve")
def approve(
    item_id: int,
    request: Request,
    body: ApproveBody | None = None,
    cfg: Config = Depends(get_cfg),
    db: Db = Depends(get_db),
):
    item = _item(db, item_id)
    try:
        with request.app.state.pending_lock:  # check, commit and status update must not interleave
            if item.kind == "statement":
                result = approve_statement(item_id, cfg, db, CsvFinanceStore(cfg.finance_dir))
            elif item.kind == "bundle":
                selected = body.selected if body else None
                result = approve_bundle(
                    item_id,
                    selected,
                    cfg.data_repo,
                    db,
                    date.today(),
                    CsvFinanceStore(cfg.finance_dir),
                )
            else:
                result = approve_pending(item_id, cfg.data_repo, db, date.today())
    except PendingError as e:
        raise HTTPException(409, str(e)) from e
    if item.kind == "statement":
        text = f"Imported {item.payload['file']}. You approved it."
        after_import(request.app.state, cfg)
    elif item.kind == "bundle":
        text = f"Saved {item.payload['title']}. You approved it."
        if item.payload.get("section") == "categories":
            _in_background(push_from_config, cfg)  # stored rows got categories
    else:
        text = f"Saved a memory: {item.payload['text']}. You approved it."
    db.add_activity("pending", text, datetime.now())
    return {"result": result}


@router.post("/pending/{item_id}/reject")
def reject(item_id: int, request: Request, db: Db = Depends(get_db)):
    item = _item(db, item_id)
    try:
        with request.app.state.pending_lock:
            if item.kind == "statement":
                reject_statement(item_id, db)
            elif item.kind == "bundle":
                reject_bundle(item_id, db)
            else:
                reject_pending(item_id, db)
    except PendingError as e:
        raise HTTPException(409, str(e)) from e
    label = {"bundle": "title", "statement": "file"}.get(item.kind, "text")
    label = item.payload[label]
    db.add_activity("pending", f"Did not save: {label}. You rejected it.", datetime.now())
    return {}


def _in_background(fn, *args) -> None:
    import threading

    threading.Thread(target=fn, args=args, daemon=True).start()


def after_import(state, cfg: Config) -> None:
    """Copy to the Sheet and suggest categories in the background; approve does not wait."""
    _in_background(push_from_config, cfg)
    if not cfg.flags.get("category_suggestions"):
        return

    from server.finance.suggest import (
        not_pending,
        queue_suggestions,
        suggest_categories,
        uncategorised,
    )

    factory = state.private_factory or state.adapter_factory  # merchant texts are finance data

    def work() -> None:
        db = Db(cfg.db_path)
        try:
            merchants = not_pending(db, uncategorised(CsvFinanceStore(cfg.finance_dir)))
            if merchants:
                cats = suggest_categories(merchants, load_data(cfg.data_repo), factory())
                queue_suggestions(db, cats, [], "import", datetime.now())
        except Exception:  # suggestions are optional; the import is already saved
            import logging

            logging.getLogger(__name__).exception("suggestions after import failed")
        finally:
            db.conn.close()

    _in_background(work)
