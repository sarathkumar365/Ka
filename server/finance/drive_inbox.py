"""Drive statement inbox: new PDFs become import cards in Pending; nothing is written unapproved."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.integrations.google.drive import DriveClient
from server.integrations.google.oauth import require_drive
from server.locks import user_lock
from server.memory.pending import PendingError
from server.store.db import Db

from .importer import ImportFailed, commit_import, prepare_import
from .parser import StatementFormatError
from .store import FinanceStore

KIND = "statement"
SEEN = "drive_seen"
LAST_SYNC = "drive_sync"


@dataclass
class SyncResult:
    new: int = 0
    skipped: list[str] = field(default_factory=list)


def _dest(folder: Path, name: str, file_id: str) -> Path:
    safe = re.sub(r"[^\w.\- ]", "_", Path(name).name) or "statement.pdf"
    dest = folder / safe
    return dest if not dest.exists() else folder / f"drive-{file_id[:8]}-{safe}"


def _card(name: str, preview) -> dict:
    s = preview.statement
    return {
        "file": name,
        "path": "",
        "statement_id": s.statement_id,
        "account": s.account,
        "period_start": s.period_start.isoformat(),
        "period_end": s.period_end.isoformat(),
        "rows": len(preview.transactions),
        "money_in": str(s.total_deposits),
        "money_out": str(s.total_withdrawals),
        "checks": [f"{f.check} row {f.row_number}: {f.message}" for f in preview.failures],
        "unknown_merchants": len(preview.unknown_merchants),
        "already_imported": preview.already_imported,
    }


def sync_drive(drive: DriveClient, cfg: Config, db: Db, now: datetime) -> SyncResult:
    from .store import CsvFinanceStore

    result = SyncResult()
    with user_lock("drive_sync", cfg.user_id):  # the job and Sync now can overlap
        seen = set(json.loads(db.get_state(SEEN) or "[]"))
        cfg.statements_dir.mkdir(parents=True, exist_ok=True)
        store = CsvFinanceStore(cfg.finance_dir, cfg.user_id)
        data = load_data(cfg.data_repo)
        for f in drive.list_pdfs(require_drive(cfg)):
            if f.id in seen:
                continue
            dest = _dest(cfg.statements_dir, f.name, f.id)
            try:
                drive.download(f.id, dest)
                preview = prepare_import(dest, data, store)
            except (StatementFormatError, ImportFailed) as e:
                result.skipped.append(f"{f.name}: {e}")  # not a usable statement: skip for good
                dest.unlink(missing_ok=True)
            except Exception as e:  # noqa: BLE001  download or read failed: try this file next sync
                result.skipped.append(f"{f.name}: will retry ({type(e).__name__})")
                dest.unlink(missing_ok=True)
                continue
            else:
                payload = _card(f.name, preview) | {"path": dest.name}
                db.add_pending(KIND, payload, "drive", now, f"drive:{f.id}")
                result.new += 1
            seen.add(f.id)
            db.set_state(SEEN, json.dumps(sorted(seen)))
        summary = {"at": now.isoformat(), "new": result.new, "skipped": result.skipped}
        db.set_state(LAST_SYNC, json.dumps(summary))
    return result


def _statement_card(db: Db, item_id: int):
    item = db.get_pending(item_id)
    if item is None or item.status != "pending" or item.kind != KIND:
        raise PendingError(f"no pending statement {item_id}")
    return item


def approve_statement(item_id: int, cfg: Config, db: Db, store: FinanceStore) -> str:
    card = _statement_card(db, item_id)
    pdf = cfg.statements_dir / card.payload["path"]
    try:
        # Re-read the file: the store may have changed since the card was made.
        preview = prepare_import(pdf, load_data(cfg.data_repo), store)
        if preview.already_imported:
            db.set_pending_status(item_id, "rejected")  # a duplicate card closes itself
            raise PendingError(f"already imported: {preview.statement.statement_id}; card closed")
        n = commit_import(preview, store)
    except (StatementFormatError, ImportFailed) as e:
        raise PendingError(str(e)) from e
    db.set_pending_status(item_id, "approved")
    return f"imported {n} rows from {card.payload['file']}"


def refresh_imported(rows: list[dict], store: FinanceStore) -> list[dict]:
    """already_imported as of now, not as of the sync: another copy may have been imported since."""
    done = {s.statement_id for s in store.statements()}
    return [r | {"already_imported": r["statement_id"] in done} for r in rows]


def reject_statement(item_id: int, db: Db) -> None:
    _statement_card(db, item_id)
    db.set_pending_status(item_id, "rejected")


def run_sync(cfg: Config, now: datetime) -> SyncResult:
    """Sign in, sync, and record any failure in drive_sync so Settings can show it."""
    from server.integrations.google.drive import ApiDrive
    from server.integrations.google.oauth import auth_for

    db = Db(cfg.db_path, cfg.user_id)
    try:
        return sync_drive(ApiDrive(auth_for(cfg).credentials()), cfg, db, now)
    except Exception as e:
        reason = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        db.set_state(LAST_SYNC, json.dumps({"at": now.isoformat(), "error": reason}))
        raise
    finally:
        db.conn.close()


def drive_job(cfg: Config):
    import logging

    from server.integrations.google.oauth import GoogleSetupMissing
    from server.scheduler import ScheduledJob

    def run() -> None:
        try:
            run_sync(cfg, datetime.now())
        except GoogleSetupMissing:  # expected until the account sets its folder; Settings shows it
            logging.getLogger(__name__).info("drive sync skipped for %s: no folder set", cfg.user_id)
        except Exception:  # recorded in drive_sync; a background job must never crash the server
            logging.getLogger(__name__).exception("drive sync failed")

    return ScheduledJob("drive_sync", {"trigger": "interval", "minutes": 30}, run)
