"""Runs one intake job (documents or pasted memory) and records progress in `intake_jobs`."""

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from server.agent.adapters import Adapter
from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.store.db import Db

from .extract import extract_resume
from .memory_import import import_memory
from .queue import queue_draft
from .readers import IntakeError, is_statement, read_document

log = logging.getLogger(__name__)
GENERIC = "Something went wrong."


def _delete(paths: list[Path]) -> None:
    for p in paths:
        p.unlink(missing_ok=True)
    for folder in {p.parent for p in paths}:
        try:
            folder.rmdir()  # only removes an empty per-job folder
        except OSError:
            pass


def run_documents_job(
    job_id: str,
    paths: list[Path],
    cfg: Config,
    adapter: Adapter,
    now: Callable[[], datetime] = datetime.now,
) -> None:
    db = Db(cfg.db_path)
    try:
        db.update_intake_job(job_id, status="running", step="Starting")
        data = load_data(cfg.data_repo)
        warnings: list[str] = []
        cards, skipped = 0, []
        drafts = []
        for path in paths:  # read and extract every file first, so a late failure queues nothing
            if is_statement(path):
                warnings.append(f"{path.name} is a bank statement; use the statement import")
                continue
            db.update_intake_job(job_id, step=f"Reading {path.name}")
            text = read_document(path)
            db.update_intake_job(job_id, step="Finding jobs and highlights")
            draft, found = extract_resume(text, adapter, [d.name for d in data.jobs.domains])
            warnings += [f"{path.name}: {w}" for w in found]
            db.update_intake_job(job_id, step=f"Found {len(draft.jobs)} job(s)")
            drafts.append((path, draft))
        if not drafts and not warnings:
            raise IntakeError("no readable documents")
        for path, draft in drafts:
            result = queue_draft(db, data, draft, path.name, now(), job_id)
            cards += result.cards
            skipped += result.skipped
        db.update_intake_job(
            job_id,
            status="done",
            step="Done",
            result={"cards": cards, "skipped": skipped, "warnings": warnings},
        )
    except IntakeError as e:
        db.update_intake_job(job_id, status="failed", message=str(e))
    except Exception:
        log.exception("intake job %s failed", job_id)
        db.update_intake_job(job_id, status="failed", message=GENERIC)
    finally:
        _delete(paths)
        db.conn.close()


def run_memory_job(
    job_id: str,
    sources: list[tuple[str, str]],
    cfg: Config,
    adapter: Adapter,
    now: Callable[[], datetime] = datetime.now,
) -> None:
    """One job for every pasted export: each source in turn; one failing source is a warning."""
    db = Db(cfg.db_path)
    try:
        data = load_data(cfg.data_repo)
        seen: list[str] = []
        cards, warnings = 0, []
        for n, (source, text) in enumerate(sources, 1):
            step = f"Reading {source} ({n} of {len(sources)})"
            db.update_intake_job(job_id, status="running", step=step)
            try:
                cards += import_memory(text, source, db, data, adapter, now(), seen)
            except IntakeError as e:
                warnings.append(f"{source}: {e}")
        if len(warnings) == len(sources):
            db.update_intake_job(job_id, status="failed", message="; ".join(warnings))
            return
        result = {"cards": cards, "skipped": [], "warnings": warnings}
        db.update_intake_job(job_id, status="done", step="Done", result=result)
    except Exception:
        log.exception("intake job %s failed", job_id)
        db.update_intake_job(job_id, status="failed", message=GENERIC)
    finally:
        db.conn.close()
