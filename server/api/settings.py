from fastapi import APIRouter, Depends

from server.config import Config
from server.flags import FLAGS, is_on
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()


@router.get("/settings")
def get_settings(cfg: Config = Depends(get_cfg), db: Db = Depends(get_db)):
    return {
        "models": {k: {"provider": m.provider, "model": m.model} for k, m in cfg.models.items()},
        "private_models": [{"provider": m.provider, "model": m.model} for m in cfg.private_models],
        "flags": {name: is_on(cfg, name) for name in FLAGS},
        "loops_paused": db.get_state("loops_paused") == "1",
        "google": {
            "drive_folder_id": cfg.google.drive_folder_id if cfg.google else None,
            "sheet_id": cfg.google.sheet_id if cfg.google else None,
        },
        "flag_info": [
            {"name": n, "description": f.description, "on": is_on(cfg, n)} for n, f in FLAGS.items()
        ],
    }
