"""Login, logout and the one-time account setup that starts onboarding."""



from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth.middleware import COOKIE, is_local_http, now
from server.auth.ratelimit import LoginLimiter
from server.auth.sessions import expires_at, new_session, resolve, revoke
from server.auth.users import (
    MIN_PASSWORD,
    USERNAME,
    AuthError,
    authenticate,
    create_user,
    user_count,
)
from server.store.db import Db
from server.store.migrations import backfill_user
from server.users import UserError, claim_legacy_data

router = APIRouter()
limiter = LoginLimiter()


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _set_cookie(request: Request, response: Response, db: Db, token: str) -> None:
    max_age = int(((expires_at(db, token) or now()) - now()).total_seconds())
    response.set_cookie(
        COOKIE, token, max_age=max_age, path="/", httponly=True, samesite="lax",
        secure=not is_local_http(request),
    )  # fmt: skip


def _sysdb(request: Request) -> Db:
    return Db.system(request.app.state.cfg.db_path, shared_threads=True)


@router.get("/auth/status")
def status(request: Request):
    db = _sysdb(request)
    try:
        user = resolve(db, request.cookies.get(COOKIE), now())
        return {
            "setup_needed": user_count(db) == 0, "user": user, "min_password": MIN_PASSWORD,
            "username_rule": USERNAME.pattern,
        }
    finally:
        db.conn.close()


@router.post("/auth/setup")
def setup(body: Credentials, request: Request, response: Response):
    cfg = request.app.state.cfg
    db = _sysdb(request)
    try:
        if user_count(db):
            raise HTTPException(409, "an account already exists")
        if not USERNAME.match(body.username) or len(body.password) < MIN_PASSWORD:
            try:  # create_user owns the messages; this only runs its checks early
                create_user(Db.system(":memory:"), body.username, body.password, now())
            except AuthError as e:
                raise HTTPException(422, str(e)) from None
        try:
            claim_legacy_data(cfg, body.username)
        except UserError as e:
            raise HTTPException(409, str(e)) from None
        user_id = create_user(db, body.username, body.password, now())
        backfill_user(db.conn, user_id)
        request.app.state.on_user_created(user_id)
        token = new_session(db, user_id, now(), request.headers.get("user-agent"))
        _set_cookie(request, response, db, token)
        return {"user": user_id}
    finally:
        db.conn.close()


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response):
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client, now()):
        raise HTTPException(429, "too many attempts, try again later")
    db = _sysdb(request)
    try:
        try:
            user_id = authenticate(db, body.username, body.password, now())
        except AuthError as e:
            raise HTTPException(401, str(e)) from None
        token = new_session(db, user_id, now(), request.headers.get("user-agent"))
        _set_cookie(request, response, db, token)
        return {"user": user_id}
    finally:
        db.conn.close()


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        db = _sysdb(request)
        try:
            revoke(db, token)
        finally:
            db.conn.close()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


