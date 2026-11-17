"""Onboarding intake: upload documents or paste memory, poll the job, queue basics."""

import shutil
import threading
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from server.agent.adapters import AdapterError
from server.config import Config
from server.intake.queue import queue_basics
from server.intake.readers import SUPPORTED
from server.intake.runner import run_documents_job, run_memory_job
from server.integrations.data_repo.loader import load_data
from server.store.db import Db

from .deps import get_cfg, get_db

router = APIRouter()
MAX_FILES = 5
MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 60_000


def _on(request: Request) -> None:
    if not request.app.state.cfg.flags.get("intake"):
        raise HTTPException(404, "intake is off")


class MemoryBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    source: str = Field(default="assistant", max_length=40)


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
    with request.app.state.lock:
        if db.running_intake_job():
            raise HTTPException(409, "another intake job is running")
        return db.new_intake_job(kind, datetime.now())  # type: ignore[arg-type]


@router.post("/intake/documents")
def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    cfg: Config = Depends(get_cfg),
    db: Db = Depends(get_db),
):
    _on(request)
    if not 1 <= len(files) <= MAX_FILES:
        raise HTTPException(400, f"send between 1 and {MAX_FILES} files")
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
    adapter = _adapter(request)
    job_id = _start(request, db, "documents")
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
    threading.Thread(
        target=run_documents_job, args=(job_id, paths, cfg, adapter), daemon=True
    ).start()
    return {"job_id": job_id}


@router.post("/intake/memory")
def paste_memory(
    body: MemoryBody,
    request: Request,
    cfg: Config = Depends(get_cfg),
    db: Db = Depends(get_db),
):
    _on(request)
    adapter = _adapter(request)
    job_id = _start(request, db, "memory")
    threading.Thread(
        target=run_memory_job,
        args=(job_id, body.text, body.source, cfg, adapter),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@router.post("/intake/basics")
def basics(
    body: BasicsBody,
    request: Request,
    cfg: Config = Depends(get_cfg),
    db: Db = Depends(get_db),
):
    _on(request)
    data = load_data(cfg.data_repo)
    n = queue_basics(
        db, data, body.name, body.city, body.region, body.country, body.role, datetime.now()
    )
    return {"cards": n}


@router.get("/intake/{job_id}")
def job_status(job_id: str, request: Request, db: Db = Depends(get_db)):
    _on(request)
    job = db.get_intake_job(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return asdict(job)
