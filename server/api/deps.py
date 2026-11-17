from collections.abc import Iterator

from fastapi import Request

from server.config import Config
from server.store.db import Db


def get_cfg(request: Request) -> Config:
    return request.app.state.cfg


def get_db(request: Request) -> Iterator[Db]:
    db = Db(request.app.state.cfg.db_path, shared_threads=True, init_schema=False)
    try:
        yield db
    finally:
        db.conn.close()
