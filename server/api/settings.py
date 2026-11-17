from fastapi import APIRouter, Depends

from server.config import Config

from .deps import get_cfg

router = APIRouter()


@router.get("/settings")
def get_settings(cfg: Config = Depends(get_cfg)):
    return {
        "models": {k: {"provider": m.provider, "model": m.model} for k, m in cfg.models.items()},
        "private_models": [{"provider": m.provider, "model": m.model} for m in cfg.private_models],
        "flags": cfg.flags,
    }
