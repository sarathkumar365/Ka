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
from server.flags import is_on
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


UPLOAD_LIMIT = 5 * 10 * 1024 * 1024 + 1024 * 1024  # five files of 10 MB plus form overhead
# The onboarding send also carries up to five 60k memory pastes and the basics.
UPLOAD_PATHS = {
    "/api/intake/onboarding": UPLOAD_LIMIT + 5 * 60_000 + 64 * 1024,
}
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


def create_app(
    cfg: Config,
    adapter_factory: Callable[[], Adapter],
    approval_timeout: float = 600.0,
    start_scheduler: bool = False,
    private_factory: Callable[[], Adapter] | None = None,
    small_factory: Callable[[], Adapter] | None = None,
) -> FastAPI:
    from server.auth.middleware import require_session
    from server.tracing import traced_factory

    from . import activity, auth, chat, conversations, google, intake, loops, onboarding, pending
    from . import settings as settings_api
    from .approvals import ApprovalBroker

    adapter_factory = traced_factory(cfg, adapter_factory, "chat")
    private_factory = traced_factory(cfg, private_factory, "private")
    # The small tier does background sorting (nightly extraction); chats stay on the main model.
    small_factory = traced_factory(cfg, small_factory, "small") or adapter_factory
    jobs = _jobs(cfg, small_factory, private_factory) if start_scheduler else []
    run_loops = start_scheduler and is_on(cfg, "loops")
    if run_loops:
        from server.scheduler import ScheduledJob

        jobs.append(ScheduledJob("loop_watchdog", {"trigger": "interval", "minutes": 15},
                                 lambda: _for_each_user(cfg, _watch)))  # fmt: skip
    lifespan = _lifespan(cfg, jobs, (adapter_factory, private_factory) if run_loops else None)
    app = FastAPI(title="Ka", docs_url=None, redoc_url=None, lifespan=lifespan)
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

    # Added after the checks above, so it runs before them: no session, no further work.
    app.middleware("http")(require_session)

    @app.middleware("http")
    async def cap_upload_size(request, call_next):
        # Starlette spools a multipart body to disk before the handler runs, so refuse early.
        if request.url.path in UPLOAD_PATHS and request.method == "POST":
            length = request.headers.get("content-length")
            if length is None:
                return JSONResponse({"detail": "content-length required"}, status_code=411)
            if int(length) > UPLOAD_PATHS[request.url.path]:
                return JSONResponse({"detail": "upload is too large"}, status_code=413)
        return await call_next(request)

    boot = Db.system(cfg.db_path)  # create the schema once; request connections skip it
    boot.fail_interrupted_intake_jobs()  # a restart killed any running job's thread
    boot.conn.close()
    app.state.cfg = cfg
    app.state.adapter_factory = adapter_factory
    app.state.private_factory = private_factory
    app.state.broker = ApprovalBroker()
    app.state.approval_timeout = approval_timeout
    app.state.running = set()
    app.state.lock = threading.Lock()
    app.state.pending_lock = threading.Lock()
    app.state.on_user_created = lambda user_id: None  # loops add their built-in tasks here
    for module in (
        auth,
        conversations,
        pending,
        activity,
        settings_api,
        chat,
        intake,
        onboarding,
        loops,
        google,
    ):
        app.include_router(module.router, prefix="/api")
    if UI_DIST.is_dir():
        app.mount("/", SPAStatic(directory=UI_DIST, html=True), name="ui")
    return app


def _jobs(cfg: Config, adapter_factory, private_factory) -> list:
    from server.finance.drive_inbox import drive_job
    from server.scheduler import ScheduledJob, nightly_job

    jobs = []
    if is_on(cfg, "nightly_extraction"):
        nightly = _as_owner(
            cfg, lambda u: nightly_job(u, adapter_factory, private_factory=private_factory)
        )
        # The catch-up runs in the scheduler thread right after start, so boot never waits on it.
        jobs += [
            ScheduledJob(
                "nightly_extraction", {"trigger": "cron", "hour": 3, "minute": 0}, nightly
            ),
            ScheduledJob("catch_up", {"trigger": "date"}, nightly),
        ]
    # With loops on, the statement import loop owns the Drive folder; the old job stays for "off".
    if is_on(cfg, "google") and cfg.google is not None and not is_on(cfg, "loops"):
        jobs.append(
            ScheduledJob(
                "drive_sync", {"trigger": "interval", "minutes": 30}, _as_owner(cfg, drive_job)
            )
        )
    return jobs


def _as_owner(cfg: Config, make):
    """Run a job as the account (resolved at run time: there may be none at boot)."""
    from server.users import UserError, only_user, user_config

    made: dict[
        str, object
    ] = {}  # one job per user, so its own lock spans the catch-up and cron run

    def run() -> None:
        try:
            user = only_user(Db.system(cfg.db_path))
        except UserError:
            return
        if user not in made:
            made[user] = make(user_config(cfg, user))
        made[user].run()

    return run


def _users(cfg: Config) -> list[str]:
    db = Db.system(cfg.db_path)
    try:
        return [r[0] for r in db.conn.execute("select id from users order by created_at")]
    finally:
        db.conn.close()


def _for_each_user(cfg: Config, fn) -> None:
    for user in _users(cfg):
        fn(cfg, user)


def _watch(cfg: Config, user: str) -> None:
    from server.loops.service import watchdog

    watchdog(cfg, user)


def _start_loops(app, scheduler, cfg: Config, factories) -> None:
    """Schedule every user's tasks and keep them in sync while the server runs."""
    from datetime import datetime

    from server.loops import triggers
    from server.loops.builtin import ensure_builtin_tasks
    from server.loops.service import execute
    from server.loops.tasks import TaskStore

    adapter_factory, private_factory = factories
    loops = triggers.LoopScheduler(
        scheduler, cfg, lambda user, task_id: execute(cfg, user, task_id, adapter_factory, private_factory)
    )
    triggers.ACTIVE = loops

    def added(user: str) -> None:
        db = Db(cfg.db_path, user)
        try:
            ensure_builtin_tasks(TaskStore(db), datetime.now())
        finally:
            db.conn.close()
        loops.sync(user)

    for user in _users(cfg):
        added(user)
    app.state.on_user_created = added
    app.state.loops = loops


def _lifespan(cfg: Config, jobs: list, loop_factory=None):
    from contextlib import asynccontextmanager

    from server.scheduler import start_scheduler
    from server.tracing import setup_tracing, shutdown_tracing

    @asynccontextmanager
    async def lifespan(_app):
        traced = setup_tracing(cfg)
        scheduler = start_scheduler(jobs) if jobs else None
        if scheduler is not None and loop_factory is not None:
            _start_loops(_app, scheduler, cfg, loop_factory)
        try:
            yield
        finally:
            from server.loops import triggers

            triggers.ACTIVE = None
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            if traced:
                shutdown_tracing()

    return lifespan
