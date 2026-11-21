"""Onboarding intake: one send with basics, documents and memory exports; poll the job."""

import shutil
import threading
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from server.agent.adapters import AdapterError
from server.config import Config
from server.flags import is_on
from server.intake.readers import SUPPORTED
from server.intake.runner import Basics, run_onboarding_job
from server.locks import user_lock
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()
MAX_FILES = 5
MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 60_000


def _on(request: Request) -> None:
    if not is_on(request.state.cfg, "intake"):
        raise HTTPException(404, "intake is off")


class MemoryItem(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    source: str = Field(default="assistant", min_length=1, max_length=40)


class BasicsBody(BaseModel):
    name: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=100)
    region: str = Field(default="", max_length=100)
    country: str = Field(default="", max_length=100)
    role: str = Field(default="", max_length=300)


def _adapter(request: Request):
    try:
        return request.app.state.adapter_factory()
    except AdapterError as e:
        raise HTTPException(503, str(e)) from e


def _start(request: Request, db: Db, kind: str) -> str:
    """Create the job row unless one is already running; the check and insert are atomic."""
    with user_lock("intake", db.user_id):
        if db.running_intake_job():
            raise HTTPException(409, "another intake job is running")
        return db.new_intake_job(kind, datetime.now())  # type: ignore[arg-type]


def _read_files(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        name = (f.filename or "file").replace("\\", "/").split("/")[-1]
        suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in SUPPORTED:
            raise HTTPException(400, f"{name}: unsupported file type")
        data = f.file.read(MAX_BYTES + 1)
        if not data.strip():
            raise HTTPException(400, f"{name}: the file is empty")
        if len(data) > MAX_BYTES:
            raise HTTPException(400, f"{name}: larger than 10 MB")
        blobs.append((name, data))
    return blobs


def _save(cfg: Config, db: Db, job_id: str, blobs: list[tuple[str, bytes]]) -> list:
    folder = cfg.data_repo / "local" / "intake" / job_id
    try:
        folder.mkdir(parents=True)
        paths = []
        for name, data in blobs:
            path = folder / name
            path.write_bytes(data)
            paths.append(path)
    except OSError:
        shutil.rmtree(folder, ignore_errors=True)
        db.update_intake_job(job_id, status="failed", message="could not save the upload")
        raise HTTPException(500, "could not save the upload") from None
    return paths


@router.get("/intake/{job_id}")
def job_status(job_id: str, request: Request, db: Db = Depends(get_db)):
    _on(request)
    job = db.get_intake_job(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return asdict(job)


MEMORY_LIST = TypeAdapter(list[MemoryItem])
BASICS = TypeAdapter(BasicsBody)


def _json_field(adapter: TypeAdapter, raw: str | None, what: str):
    if not raw:
        return None
    try:
        return adapter.validate_json(raw)
    except ValidationError:
        raise HTTPException(422, f"{what} is not valid") from None


@router.post("/intake/onboarding")
def send_onboarding(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    basics: str | None = Form(default=None),
    memory: str | None = Form(default=None),
    cfg: Config = Depends(get_cfg),
    db: Db = Depends(get_db),
):
    """Everything from the onboarding screen in one request, read by one job."""
    _on(request)
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"send at most {MAX_FILES} files")
    body = _json_field(BASICS, basics, "basics")
    items = _json_field(MEMORY_LIST, memory, "memory") or []
    if len(items) > 5:
        raise HTTPException(422, "at most 5 memory exports")
    filled = body is not None and any(v.strip() for v in body.model_dump().values())
    if not files and not filled and not items:
        raise HTTPException(400, "nothing to send")
    blobs = _read_files(files)
    adapter = _adapter(request)
    job_id = _start(request, db, "onboarding")
    paths = _save(cfg, db, job_id, blobs) if blobs else []
    threading.Thread(
        target=run_onboarding_job,
        args=(
            job_id,
            paths,
            Basics(**body.model_dump()) if filled else None,
            [(i.source, i.text) for i in items],
            cfg,
            adapter,
        ),
        daemon=True,
    ).start()
    return {"job_id": job_id}
