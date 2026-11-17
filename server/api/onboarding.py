"""First-run check: should the app open on the Onboarding screen?"""

from fastapi import APIRouter, Depends

from server.config import Config
from server.integrations.data_repo.loader import DataRepoError, load_data
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()
DONE = "onboarding_done"


@router.get("/onboarding/status")
def status(cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)):
    if not cfg.flags.get("intake"):
        return {"needed": False, "reason": "off"}
    if db.get_state(DONE) == "1":
        return {"needed": False, "reason": "done"}
    try:
        has_jobs = bool(load_data(cfg.data_repo).jobs.jobs)
    except (DataRepoError, OSError):  # never trap the owner behind a check that cannot run
        return {"needed": False, "reason": "unavailable"}
    if has_jobs:
        return {"needed": False, "reason": "has_data"}
    return {"needed": True, "reason": "first_run"}


@router.post("/onboarding/complete")
def complete(db: Db = Depends(get_db)):
    db.set_state(DONE, "1")
    return {"ok": True}
