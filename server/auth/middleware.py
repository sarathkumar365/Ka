"""Every /api route needs a valid session, except the few that let you log in."""

from datetime import datetime

from starlette.responses import JSONResponse

from server.store.db import Db
from server.users import user_config

from .sessions import resolve

COOKIE = "ka_session"
OPEN = {"/api/auth/status", "/api/auth/login", "/api/auth/setup", "/api/auth/logout"}


def now() -> datetime:
    return datetime.now()


def is_local_http(request) -> bool:
    return request.url.scheme == "http" and request.url.hostname in ("localhost", "127.0.0.1")


async def require_session(request, call_next):
    path = request.url.path
    request.state.user_id = None
    if not path.startswith("/api/") or path in OPEN:
        return await call_next(request)
    base = request.app.state.cfg
    db = Db.system(base.db_path, shared_threads=True)
    try:
        user_id = resolve(db, request.cookies.get(COOKIE), now())
    finally:
        db.conn.close()
    if user_id is None:
        return JSONResponse({"detail": "not signed in"}, status_code=401)
    request.state.user_id = user_id
    request.state.cfg = user_config(base, user_id)
    return await call_next(request)
