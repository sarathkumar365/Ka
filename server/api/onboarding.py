"""First-run check: should the app open on the Onboarding screen?"""

from fastapi import APIRouter, Depends

from server.config import Config
from server.integrations.data_repo.loader import DataRepoError, load_data
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()
FINANCE_SECTIONS = {"categories", "types"}


@router.get("/onboarding/status")
def status(cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)):
    """Decided from the data, not a one-time flag: while Ka knows nothing about the owner, it
    opens on Onboarding. Finance rows do not count; they say nothing about who the owner is."""
    if not cfg.flags.get("intake"):
        return {"needed": False, "reason": "off"}
    try:
        d = load_data(cfg.data_repo)
    except (DataRepoError, OSError):  # never trap the owner behind a check that cannot run
        return {"needed": False, "reason": "unavailable"}
    if d.profile.name.strip() or d.education.entries or d.jobs.jobs or d.memory.entries:
        return {"needed": False, "reason": "has_data"}
    # A sent onboarding: still reading, or its cards wait for review. Statement and category
    # cards come from finance and say nothing about the owner, so they do not hold setup back.
    about_owner = [
        i
        for i in db.list_pending()
        if i.kind != "statement" and i.payload.get("section") not in FINANCE_SECTIONS
    ]
    if db.running_intake_job() or about_owner:
        return {"needed": False, "reason": "pending"}
    return {"needed": True, "reason": "first_run"}
