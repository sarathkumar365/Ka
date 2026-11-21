"""Copy the finance store to the Google Sheet. The CSV stays the truth; a failed copy only waits."""

import json
import logging
from datetime import datetime

from server.config import Config
from server.flags import is_on
from server.integrations.google.sheets import SheetsClient
from server.locks import user_lock
from server.store.db import Db

from .models import StatementRecord, Transaction
from .store import FinanceStore

STATUS = "sheet_status"
log = logging.getLogger(__name__)


def _table(model, items) -> tuple[list[str], list[list[str]]]:
    header = list(model.model_fields)
    return header, [[str(getattr(i, f)) for f in header] for i in items]


def push_sheet(
    sheets: SheetsClient, sheet_id: str, store: FinanceStore, db: Db, now: datetime
) -> bool:
    try:
        for tab, model, items in (
            ("Statements", StatementRecord, store.statements()),
            ("Transactions", Transaction, store.transactions()),
        ):
            header, rows = _table(model, items)
            sheets.replace_tab(sheet_id, tab, header, rows)
    except Exception as e:  # noqa: BLE001  any API or network failure: record it, never raise
        reason = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        db.set_state(STATUS, json.dumps({"at": now.isoformat(), "error": reason}))
        db.add_activity("sheet", f"Sheet copy failed: {reason}", now)
        return False
    db.set_state(STATUS, json.dumps({"at": now.isoformat(), "ok": True}))
    return True


def push_from_config(cfg: Config) -> bool:
    """Sign in and copy; used after imports and recategorising when the google flag is on."""

    if not is_on(cfg, "google") or cfg.google is None:
        return False
    # Copies replace whole tabs: the store is read inside the lock, so the newest copy wins.
    with user_lock("sheet_push", cfg.user_id):
        return _push_locked(cfg)


def _push_locked(cfg: Config) -> bool:
    from server.integrations.google.oauth import GoogleAuthError, auth_for, require_sheet
    from server.integrations.google.sheets import ApiSheets

    from .store import CsvFinanceStore

    db = Db(cfg.db_path, cfg.user_id)
    try:
        try:
            sheet_id = require_sheet(cfg)
            sheets = ApiSheets(auth_for(cfg).credentials())
        except GoogleAuthError as e:
            db.set_state(STATUS, json.dumps({"at": datetime.now().isoformat(), "error": str(e)}))
            return False
        return push_sheet(
            sheets, sheet_id, CsvFinanceStore(cfg.finance_dir, cfg.user_id), db, datetime.now()
        )
    finally:
        db.conn.close()
