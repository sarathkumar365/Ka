"""Apply a bundle card to the data repo: selected items, in order, as one commit."""

from datetime import date
from pathlib import Path

from server.integrations.data_repo.loader import load_data
from server.integrations.data_repo.writer import ChangeError, Patch, apply_change, plan_batch
from server.memory.pending import PendingError
from server.store.db import Db

from .queue import KIND


def _card(db: Db, item_id: int):
    item = db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != KIND:
        raise PendingError(f"no pending card {item_id}")
    return item


def approve_bundle(
    item_id: int, selected: list[str] | None, root: Path, db: Db, today: date
) -> str:
    card = _card(db, item_id)
    p = card.payload
    if p.get("blocked"):
        raise PendingError(p["blocked"])
    for needed in p.get("needs", []):
        other = db.get_pending(needed)
        if other is not None and other.status == "pending":
            raise PendingError("approve or reject the Domains card first")
    items = p["items"]
    ids = [i["id"] for i in items]
    chosen = [i["id"] for i in items if i.get("selected")] if selected is None else selected
    if any(c not in ids for c in chosen):
        raise PendingError("selection does not match this card")
    if p["section"] == "job" and items[0]["id"] not in chosen:
        raise PendingError("a job card needs its job line selected")
    if not chosen:
        raise PendingError("nothing selected")
    domains = {d.name.lower().strip(): d.id for d in load_data(root).jobs.domains}
    patches: list[Patch] = []
    for item in items:
        if item["id"] not in chosen:
            continue
        patch = Patch(**item["patch"])
        names = patch.fields.get("domains")
        if patch.target == "highlight" and names is not None:
            resolved = [domains[n.lower().strip()] for n in names if n.lower().strip() in domains]
            fields = {k: v for k, v in patch.fields.items() if k != "domains"}
            if resolved:
                fields["domains"] = resolved
            patch = patch.model_copy(update={"fields": fields})
        patches.append(patch)
    try:
        plan = plan_batch(root, patches, f"data: intake {p['title']}")
        sha = apply_change(root, plan)
    except ChangeError as e:
        raise PendingError(str(e)) from e
    db.set_pending_status(item_id, "approved")  # the commit exists; never apply it twice
    return f"committed {sha}"


def reject_bundle(item_id: int, db: Db) -> None:
    _card(db, item_id)
    db.set_pending_status(item_id, "rejected")
