import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from server.auth.clientip import trusted_proxy
from server.config import Config
from server.flags import is_on
from server.integrations.google.oauth import GoogleAuth, GoogleAuthError, auth_for
from server.store.db import Db

from .deps import get_db

router = APIRouter()


def _auth(request: Request) -> GoogleAuth:
    cfg: Config = request.state.cfg
    if not is_on(cfg, "google") or cfg.google is None:
        raise HTTPException(404, "google is off")
    # One GoogleAuth per account, kept so the web flow's state survives login to callback; each
    # holds that account's own token file.
    auths = request.app.state.google_auths
    if cfg.user_id not in auths:
        auths[cfg.user_id] = auth_for(cfg)
    return auths[cfg.user_id]


def _redirect(request: Request) -> str:
    """Back to the address the browser used, also through the tailnet HTTPS proxy."""
    proto, host = request.url.scheme, request.url.netloc
    if trusted_proxy(request):
        proto = request.headers.get("x-forwarded-proto", proto)
        host = request.headers.get("x-forwarded-host", host)
    return f"{proto}://{host}/api/google/callback"


class GoogleIds(BaseModel):
    drive_folder_id: str | None = Field(default=None, max_length=200)
    sheet_id: str | None = Field(default=None, max_length=200)


@router.put("/google/settings")
def save_settings(body: GoogleIds, request: Request):
    from server.google_settings import save_google_settings

    _auth(request)
    clean = [(v or "").strip() or None for v in (body.drive_folder_id, body.sheet_id)]
    save_google_settings(request.state.cfg, *clean)
    return {"ok": True}


@router.get("/google/status")
def status(request: Request, db: Db = Depends(get_db)):
    auth = _auth(request)
    connected = auth.connected()
    return {
        "connected": connected,
        "email": db.get_state("google_email") if connected else None,
        "drive_sync": json.loads(db.get_state("drive_sync") or "null"),
        "sheet": json.loads(db.get_state("sheet_status") or "null"),
    }


@router.get("/google/login")
def login(request: Request):
    return RedirectResponse(_auth(request).login_url(_redirect(request)))


@router.get("/google/callback")
def callback(request: Request, state: str = "", code: str = "", db: Db = Depends(get_db)):
    auth = _auth(request)
    try:
        auth.finish(code, state, _redirect(request))
    except GoogleAuthError as e:
        raise HTTPException(400, str(e)) from None
    email = auth.email()
    if email:
        db.set_state("google_email", email)
    return RedirectResponse("/settings")


@router.post("/google/disconnect")
def disconnect(request: Request, db: Db = Depends(get_db)):
    _auth(request).disconnect()
    db.set_state("google_email", "")
    return {"ok": True}


@router.post("/google/sync")
def sync(request: Request):
    from server.finance.drive_inbox import run_sync

    _auth(request)
    try:
        r = run_sync(request.state.cfg, datetime.now())
    except GoogleAuthError as e:
        raise HTTPException(409, str(e)) from None
    except Exception as e:  # noqa: BLE001  network or API failure, recorded in drive_sync
        raise HTTPException(502, f"Drive sync failed: {type(e).__name__}") from None
    return {"new": r.new, "skipped": r.skipped}


@router.post("/google/push")
def push(request: Request):
    from server.finance.sheet_copy import push_from_config

    _auth(request)
    if not push_from_config(request.state.cfg):
        raise HTTPException(502, "Sheet copy failed; see the status line")
    return {"ok": True}
