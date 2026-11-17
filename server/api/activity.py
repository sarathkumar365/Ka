from dataclasses import asdict

from fastapi import APIRouter, Depends

from server.store.db import Db

from .deps import get_db

router = APIRouter()


@router.get("/activity")
def list_activity(db: Db = Depends(get_db)):
    return [asdict(r) for r in db.list_activity()]
