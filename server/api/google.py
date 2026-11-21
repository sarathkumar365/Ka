import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

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
    # one GoogleAuth per app, so the web flow's state survives between login and callback
    if getattr(request.app.state, "google_auth", None) is None:
        request.app.state.google_auth = auth_for(cfg)
    return request.app.state.google_auth


def _redirect(request: Request) -> str:
    port = request.url.port or 80
    return f"http://127.0.0.1:{port}/api/google/callback"


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
