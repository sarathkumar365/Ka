import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from server.agent.adapters import AdapterError, build_adapter
from server.chat import chat_loop
from server.config import ConfigError, load_config
from server.env import load_env
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.finance.statements import list_statement_files
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import DataRepoError, load_data
from server.memory.extract import extract_memories
from server.memory.pending import PendingError, approve_pending, reject_pending
from server.store.db import Db

CHECKS_RUN = 4


def _check(_args: argparse.Namespace) -> int:
    load_data(load_config().data_repo)
    print("ok: 11 files")
    return 0


def _confirm(question: str) -> bool:
    try:
        return input(question).strip().lower() == "y"
    except EOFError:  # no terminal attached: treat as no
        return False


def _import(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = CsvFinanceStore(cfg.finance_dir)
    p = prepare_import(Path(args.path).expanduser(), load_data(cfg.data_repo), store)
    s = p.statement
    print(f"account {s.account}  period {s.period_start} to {s.period_end}")
    print(
        f"rows {len(p.transactions)}  withdrawals {s.total_withdrawals}  deposits {s.total_deposits}"
    )
    if p.failures:
        for f in p.failures:
            print(f"check failed: {f.check} row {f.row_number}: {f.message}")
        print("nothing written")
        return 1
    print(f"checks: {CHECKS_RUN} passed")
    if p.unknown_types:
        print("unknown types:", "; ".join(p.unknown_types))
    if p.unknown_merchants:
        print(f"uncategorised merchants: {len(p.unknown_merchants)}")
    if p.unlinked:
        print("unlinked corrections:", ", ".join(p.unlinked))
    if p.already_imported:
        print(f"already imported: {s.statement_id}")
        return 0
    if not args.yes and not _confirm(f"Write {len(p.transactions)} rows? [y/N] "):
        print("declined, nothing written")
        return 0
    print(f"written: {commit_import(p, store)} rows")
    return 0


def _statements(_args: argparse.Namespace) -> int:
    cfg = load_config()
    for f in list_statement_files(cfg, CsvFinanceStore(cfg.finance_dir)):
        print(f"{'imported' if f.imported else 'new':9}{f.name}")
    return 0


def _chat(args: argparse.Namespace) -> int:
    load_env()
    cfg = load_config()
    which = "local" if args.local else "default"
    if which not in cfg.models:
        print(f"error: no models.{which} in config.yaml")
        return 2
    chat_loop(cfg, build_adapter(cfg.models[which]), resume=args.resume)
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from server.api.app import create_app

    load_env()
    cfg = load_config()
    if not cfg.flags.get("web_ui"):
        print("error: flag web_ui is off in config.yaml")
        return 2
    if "default" not in cfg.models:
        print("error: no models.default in config.yaml")
        return 2
    model = cfg.models["default"]
    build_adapter(model)  # fail now, not on the first message, if the key is missing
    uvicorn.run(create_app(cfg, lambda: build_adapter(model)), host="127.0.0.1", port=args.port)
    return 0


def _extract(args: argparse.Namespace) -> int:
    load_env()
    cfg = load_config()
    if not cfg.flags.get("nightly_extraction"):
        print("error: flag nightly_extraction is off in config.yaml")
        return 2
    which = "local" if args.local else "default"
    if which not in cfg.models:
        print(f"error: no models.{which} in config.yaml")
        return 2
    day = date.fromisoformat(args.date) if args.date else date.today()
    n = extract_memories(
        day,
        Db(cfg.db_path),
        load_data(cfg.data_repo),
        build_adapter(cfg.models[which]),
        datetime.now(),
    )
    print(f"queued {n} item(s) from {day}")
    return 0


def _pending(args: argparse.Namespace) -> int:
    cfg = load_config()
    db = Db(cfg.db_path)
    if args.action is None:
        old = {e.id: e.text for e in load_data(cfg.data_repo).memory.entries}
        for item in db.list_pending():
            p = item.payload
            print(f"{item.id:>3}  [{p['type']}] {p['text']}")
            if p.get("replaces"):
                print(f"     replaces {p['replaces']}: {old.get(p['replaces'], '?')}")
        return 0
    try:
        if args.action == "approve":
            print(approve_pending(args.id, cfg.data_repo, db, date.today()))
        else:
            reject_pending(args.id, db)
            print(f"rejected {args.id}")
    except PendingError as e:
        print(f"error: {e}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ka")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate the data repo").set_defaults(func=_check)
    imp = sub.add_parser("import", help="import a statement PDF")
    imp.add_argument("path")
    imp.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    imp.set_defaults(func=_import)
    sub.add_parser("statements", help="list statement PDFs").set_defaults(func=_statements)
    chat = sub.add_parser("chat", help="talk to Ka in the terminal")
    chat.add_argument("--local", action="store_true", help="use the local Ollama model only")
    chat.add_argument("--resume", help="continue a saved conversation id")
    chat.set_defaults(func=_chat)
    serve = sub.add_parser("serve", help="run the web UI on localhost")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)
    ext = sub.add_parser("extract", help="queue new memories from a day's chats")
    ext.add_argument("--date", help="YYYY-MM-DD, default today")
    ext.add_argument("--local", action="store_true")
    ext.set_defaults(func=_extract)
    pend = sub.add_parser("pending", help="list, approve or reject queued memories")
    pend.add_argument("action", nargs="?", choices=["approve", "reject"])
    pend.add_argument("id", nargs="?", type=int)
    pend.set_defaults(func=_pending)
    args = parser.parse_args(argv)
    if args.command == "pending" and args.action and args.id is None:
        parser.error("pending approve|reject needs an id")
    try:
        return args.func(args)
    except (ConfigError, DataRepoError, ImportFailed, StatementFormatError, AdapterError) as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
