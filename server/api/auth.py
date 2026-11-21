"""Sign-up (then onboarding), login and logout. Anyone can create an account."""



import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth.clientip import client_ip
from server.auth.middleware import COOKIE, is_local_http, now
from server.auth.ratelimit import LoginLimiter
from server.auth.sessions import expires_at, new_session, resolve, revoke
from server.auth.users import (
    MIN_PASSWORD,
    TAKEN,
    USERNAME,
    AuthError,
    authenticate,
    create_user,
    delete_user,
)
from server.store.db import Db
from server.users import start_user_space

router = APIRouter()
LIMITS = {
    "login": (20, timedelta(minutes=10)),  # attempts per address
    "failures": (5, timedelta(minutes=15)),  # wrong passwords per address and username
    "per_user": (50, timedelta(hours=1)),  # wrong passwords per username, all addresses
    "signup": (5, timedelta(hours=1)),  # sign-ups per address
}


def _limiter(request: Request, name: str) -> LoginLimiter:
    """One limiter of each kind per app, so tests and restarts start clean."""
    limits = request.app.state.limits
    if name not in limits:
        limits[name] = LoginLimiter(*LIMITS[name])
    return limits[name]
log = logging.getLogger(__name__)


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
        row = db.conn.execute("select username from users where id=?", (user,)).fetchone()
        return {
            "user": user, "username": row[0] if row else None,
            "min_password": MIN_PASSWORD, "username_rule": USERNAME.pattern,
        }  # fmt: skip
    finally:
        db.conn.close()


@router.post("/auth/signup")
def signup(body: Credentials, request: Request, response: Response):
    client = client_ip(request)
    if not _limiter(request, "signup").allow(client, now()):
        raise HTTPException(429, "too many sign-ups, try again later")
    db = _sysdb(request)
    try:
        try:
            user_id = create_user(db, body.username, body.password, now())
        except AuthError as e:
            raise HTTPException(409 if str(e) == TAKEN else 422, str(e)) from None
        try:
            start_user_space(request.app.state.cfg, user_id)
        except Exception:
            log.exception("could not create the folder for %s", user_id)
            delete_user(db, user_id)
            raise HTTPException(500, "could not create the account, try again") from None
        try:
            request.app.state.on_user_created(user_id)
        except Exception:  # loops add the built-in tasks again on the next start
            log.exception("built-in tasks for %s not added", user_id)
        token = new_session(db, user_id, now(), request.headers.get("user-agent"))
        _set_cookie(request, response, db, token)
        return {"user": user_id}
    finally:
        db.conn.close()


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response):
    client = client_ip(request)
    pair = f"{client}|{body.username.lower()}"
    failures = _limiter(request, "failures")
    name = body.username.lower()
    per_user = _limiter(request, "per_user")
    if (
        failures.blocked(pair, now())
        or per_user.blocked(name, now())
        or not _limiter(request, "login").allow(client, now())
    ):
        raise HTTPException(429, "too many attempts, try again later")
    db = _sysdb(request)
    try:
        try:
            user_id = authenticate(db, body.username, body.password, now())
        except AuthError as e:
            failures.fail(pair, now())
            per_user.fail(name, now())
            raise HTTPException(401, str(e)) from None
        failures.clear(pair)
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


