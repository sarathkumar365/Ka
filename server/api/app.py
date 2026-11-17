"""FastAPI app: JSON endpoints over the core, SSE chat, and the built UI."""

import threading
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from server.agent.adapters import Adapter
from server.config import Config
from server.store.db import Db


class SPAStatic(StaticFiles):
    """Serve the built UI; unknown paths get index.html so client-side routes survive a reload."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code == 404 and not (path == "api" or path.startswith("api/")):
                return await super().get_response("index.html", scope)
            raise


UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


def create_app(
    cfg: Config, adapter_factory: Callable[[], Adapter], approval_timeout: float = 600.0
) -> FastAPI:
    from . import activity, chat, conversations, pending, settings
    from .approvals import ApprovalBroker

    app = FastAPI(title="Ka", docs_url=None, redoc_url=None)
    allowed = {"127.0.0.1", "localhost", *cfg.ui_hosts}
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(allowed))

    @app.middleware("http")
    async def refuse_cross_site_writes(request, call_next):
        # A page on another site can POST here with a plain fetch; browsers always send Origin.
        origin = request.headers.get("origin")
        writes = request.method not in ("GET", "HEAD", "OPTIONS")
        if writes and origin and urlsplit(origin).hostname not in allowed:
            return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        return await call_next(request)

    Db(cfg.db_path).conn.close()  # create the schema once; request connections skip it
    app.state.cfg = cfg
    app.state.adapter_factory = adapter_factory
    app.state.broker = ApprovalBroker()
    app.state.approval_timeout = approval_timeout
    app.state.running = set()
    app.state.lock = threading.Lock()
    app.state.pending_lock = threading.Lock()
    for module in (conversations, pending, activity, settings, chat):
        app.include_router(module.router, prefix="/api")
    if UI_DIST.is_dir():
        app.mount("/", SPAStatic(directory=UI_DIST, html=True), name="ui")
    return app
