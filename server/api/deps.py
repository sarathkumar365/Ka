from collections.abc import Iterator

from fastapi import HTTPException, Request

from server.config import Config
from server.store.db import Db


def get_user(request: Request) -> str:
    user = getattr(request.state, "user_id", None)
    if not user:
        raise HTTPException(401, "not signed in")
    return user


def get_cfg(request: Request) -> Config:
    """The signed-in user's view of the config (their data folder)."""
    get_user(request)
    return request.state.cfg


def get_db(request: Request) -> Iterator[Db]:
    user = get_user(request)
    db = Db(request.app.state.cfg.db_path, user, shared_threads=True, init_schema=False)
    try:
        yield db
    finally:
        db.conn.close()
