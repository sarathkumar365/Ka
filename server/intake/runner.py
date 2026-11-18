"""Runs one intake job (documents or pasted memory) and records progress in `intake_jobs`."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from server.agent.adapters import Adapter
from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.store.db import Db

from .extract import extract_resume
from .memory_import import import_memory
from .queue import KIND, queue_basics, queue_draft
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


@dataclass
class Basics:
    name: str
    city: str
    region: str
    country: str
    role: str


def _extract(paths, data, adapter, db, job_id, tolerant: bool, on=lambda i, state: None):
    """Read and extract every file before anything is queued. tolerant: a bad file is a warning.
    `on(index, state)` reports each file as reading, done or failed (the onboarding ring)."""
    drafts, warnings = [], []
    for n, path in enumerate(paths):
        on(n, "reading")
        if is_statement(path):
            warnings.append(f"{path.name} is a bank statement; use the statement import")
            on(n, "failed")
            continue
        try:
            db.update_intake_job(job_id, status="running", step=f"Reading {path.name}")
            text = read_document(path)
            db.update_intake_job(job_id, step="Finding jobs and highlights")
            draft, found = extract_resume(text, adapter, [d.name for d in data.jobs.domains])
        except IntakeError as e:
            if not tolerant:
                raise
            warnings.append(f"{path.name}: {e}")
            on(n, "failed")
            continue
        warnings += [f"{path.name}: {w}" for w in found]
        db.update_intake_job(job_id, step=f"Found {len(draft.jobs)} job(s)")
        drafts.append((path, draft))
        on(n, "done")
    return drafts, warnings


def _queue(drafts, db, data, now, job_id) -> tuple[int, list[str]]:
    cards, skipped = 0, []
    for path, draft in drafts:
        result = queue_draft(db, data, draft, path.name, now(), job_id)
        cards += result.cards
        skipped += result.skipped
    return cards, skipped


def _memory(sources, db, data, adapter, now, job_id, on=lambda i, state: None):
    seen: list[str] = []
    cards, warnings = 0, []
    for n, (source, text) in enumerate(sources, 1):
        step = f"Reading {source} ({n} of {len(sources)})"
        db.update_intake_job(job_id, status="running", step=step)
        on(n - 1, "reading")
        try:
            cards += import_memory(text, source, db, data, adapter, now(), seen)
            on(n - 1, "done")
        except IntakeError as e:
            warnings.append(f"{source}: {e}")
            on(n - 1, "failed")
    return cards, warnings


def _job_counts(db: Db, job_id: str) -> tuple[int, int]:
    """Jobs and highlights queued by this intake job, for the summary screen."""
    jobs = highlights = 0
    for card in db.list_pending():
        p = card.payload
        if card.kind != KIND or p.get("job_id") != job_id:
            continue
        if p.get("section") == "job":
            jobs += 1
            highlights += len(p["items"]) - 1
        elif p.get("section") == "highlights":
            highlights += len(p["items"])
    return jobs, highlights


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
        drafts, warnings = _extract(paths, data, adapter, db, job_id, tolerant=False)
        if not drafts and not warnings:
            raise IntakeError("no readable documents")
        cards, skipped = _queue(drafts, db, data, now, job_id)
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
        cards, warnings = _memory(sources, db, data, adapter, now, job_id)
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


def run_onboarding_job(
    job_id: str,
    paths: list[Path],
    basics: Basics | None,
    memory: list[tuple[str, str]],
    cfg: Config,
    adapter: Adapter,
    now: Callable[[], datetime] = datetime.now,
) -> None:
    """Everything from the onboarding screen in one go: basics, documents, then each memory
    export. A part that fails is a warning; the job fails only when nothing was produced."""
    db = Db(cfg.db_path)
    # One entry per thing the owner gave, in send order; the screen draws one ring arc each.
    parts = (
        ([{"label": "Basics", "state": "waiting"}] if basics is not None else [])
        + [{"label": p.name, "state": "waiting"} for p in paths]
        + [{"label": source, "state": "waiting"} for source, _ in memory]
    )
    first_file = 1 if basics is not None else 0
    first_memory = first_file + len(paths)

    def mark(i: int, state: str) -> None:
        parts[i]["state"] = state
        db.update_intake_job(job_id, result={"parts": parts})

    try:
        db.update_intake_job(job_id, status="running", step="Starting", result={"parts": parts})
        data = load_data(cfg.data_repo)
        basic_cards = 0
        if basics is not None:
            mark(0, "reading")
            db.update_intake_job(job_id, step="Saving the basics")
            b = basics
            basic_cards = queue_basics(db, data, b.name, b.city, b.region, b.country, b.role, now())
            mark(0, "done")
        drafts, warnings = _extract(
            paths,
            data,
            adapter,
            db,
            job_id,
            tolerant=True,
            on=lambda i, st: mark(first_file + i, st),
        )
        if basics is not None and basics.name.strip():
            # the owner typed their name; a second Name line from the resume card would only compete
            drafts = [
                (
                    path,
                    d.model_copy(update={"profile": d.profile.model_copy(update={"name": None})}),
                )
                for path, d in drafts
            ]
        cards, skipped = _queue(drafts, db, data, now, job_id)
        memories, more = _memory(
            memory, db, data, adapter, now, job_id, on=lambda i, st: mark(first_memory + i, st)
        )
        warnings += more
        # Failed means nothing could be read at all; reading everything and finding nothing new
        # (a retry, or a paste with nothing worth keeping) is a done job with zero cards.
        read_ok = basics is not None or drafts or len(more) < len(memory)
        if not read_ok:
            message = "; ".join(warnings) or "nothing could be read"
            db.update_intake_job(job_id, status="failed", message=message, result={"parts": parts})
            return
        jobs, highlights = _job_counts(db, job_id)
        result = {
            "cards": basic_cards + cards + memories,
            "jobs": jobs,
            "highlights": highlights,
            "memories": memories,
            "skipped": skipped,
            "warnings": warnings,
            "parts": parts,
        }
        db.update_intake_job(job_id, status="done", step="Done", result=result)
    except Exception:
        log.exception("intake job %s failed", job_id)
        db.update_intake_job(job_id, status="failed", message=GENERIC)
    finally:
        _delete(paths)
        db.conn.close()
