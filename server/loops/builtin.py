"""Tasks that ship in code. The first: import new statements from the Drive folder."""

import json
from datetime import datetime

from server.config import Config
from server.finance.drive_inbox import KIND, SEEN, _card, _dest
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import load_data
from server.integrations.google.oauth import DRIVE_MISSING
from server.store.db import Db

from .runner import RunContext
from .tasks import ScheduledTask, TaskStore

STATEMENT_IMPORT = "statement_import"
EVERY_FEW_HOURS = 180


def ensure_builtin_tasks(store: TaskStore, now: datetime) -> None:
    tid = f"{store.user}:{STATEMENT_IMPORT}"
    if store.get(tid) is None:
        task = ScheduledTask(
            name="Import new statements",
            kind="builtin",
            builtin=STATEMENT_IMPORT,
            trigger={"type": "folder", "source": "drive", "minutes": EVERY_FEW_HOURS},
            brief="Check the Drive statements folder, parse new PDFs, check totals, import.",
            toolkits=["finance"],
            checks=["row balances", "summary totals", "opening plus deposits minus withdrawals"],
            created_by="code",
        )
        store.add(task, now, task_id=tid)


def statement_import_body(
    task: ScheduledTask, rc: RunContext, drive, cfg: Config, db: Db, now: datetime
) -> dict:
    """Shadow: every new file becomes a card. Direct: a clean statement is imported at once.

    A file is claimed (its write key `drive:<id>`) only after its import or card exists, so a
    network error or a crash leaves it for the next run, and a retried run never does it twice.
    """
    out = {"new": 0, "imported": 0, "queued": 0, "skipped": []}
    if cfg.google is None or not cfg.google.drive_folder_id:
        out["skipped"].append(DRIVE_MISSING)
        return out
    cfg.statements_dir.mkdir(parents=True, exist_ok=True)
    store = CsvFinanceStore(cfg.finance_dir, cfg.user_id)
    data = load_data(cfg.data_repo)
    # Files the Drive job handled before loops existed: done already, never queued again.
    seen = set(json.loads(db.get_state(SEEN) or "[]"))
    for f in drive.list_pdfs(cfg.google.drive_folder_id):
        key = f"drive:{f.id}"
        if rc.store.write_claimed(task.id, key):
            continue
        if f.id in seen:
            rc.store.claim_write(task.id, key, rc.run_id, now)
            continue
        rc.budget.check()
        dest = _dest(cfg.statements_dir, f.name, f.id)
        try:
            drive.download(f.id, dest)
            preview = prepare_import(dest, data, store)
        except (StatementFormatError, ImportFailed) as e:
            rc.store.claim_write(task.id, key, rc.run_id, now)  # not a statement: skip for good
            out["skipped"].append(f"{f.name}: {e}")
            dest.unlink(missing_ok=True)
            continue
        except Exception as e:  # noqa: BLE001  download or read failed: next run tries again
            out["skipped"].append(f"{f.name}: will retry ({type(e).__name__})")
            dest.unlink(missing_ok=True)
            continue
        # Act first, claim after: a crash in between leaves no claim. On the retry a waiting card
        # is found here, and an import that did land shows as already imported (a card, no rows).
        if db.pending_exists(KIND, key):
            rc.store.claim_write(task.id, key, rc.run_id, now)
            continue
        clean = not preview.failures and not preview.already_imported and not preview.unknown_types
        if task.mode == "direct" and clean:
            commit_import(preview, store)
            out["imported"] += 1
            db.add_activity("loop", f"Imported {f.name} on its own", now)
        else:
            payload = _card(f.name, preview) | {"path": dest.name, "task_id": task.id}
            db.add_pending(KIND, payload, "loop", now, key)
            out["queued"] += 1
        out["new"] += 1
        rc.store.claim_write(task.id, key, rc.run_id, now)
    if out["imported"]:
        from server.finance.sheet_copy import push_from_config

        push_from_config(cfg)
    return out
