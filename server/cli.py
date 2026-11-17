import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from server.agent.adapters import AdapterError, build_adapter, build_private_adapter
from server.chat import chat_loop
from server.config import ConfigError, load_config
from server.env import load_env
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.finance.statements import list_statement_files
from server.finance.store import CsvFinanceStore
from server.intake.approve import approve_bundle, reject_bundle
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
    if cfg.flags.get("category_suggestions"):
        _queue_suggestions(cfg, store, p.unknown_merchants, p.unknown_types)
    return 0


def _queue_suggestions(cfg, store, merchants: list[str], types: list[str]) -> int:
    from server.finance.suggest import (
        not_pending,
        queue_suggestions,
        suggest_categories,
        suggest_types,
    )

    load_env()
    db = Db(cfg.db_path)
    merchants = not_pending(db, merchants)
    if not merchants and not types:
        print("nothing to suggest")
        return 0
    try:
        # merchant texts are finance data: the private chain when routing is on
        adapter = _private_adapter(cfg) or build_adapter(cfg.models["default"])
        cats = suggest_categories(merchants, load_data(cfg.data_repo), adapter)
        tags = suggest_types(types, adapter)
    except (AdapterError, ConfigError) as e:
        print(f"suggestions skipped: {e}")
        return 1
    n = queue_suggestions(db, cats, tags, "import", datetime.now())
    print(f"queued {len(cats)} category and {len(tags)} type suggestion(s) in {n} card(s)")
    return 0


def _suggest(_args: argparse.Namespace) -> int:
    from server.finance.suggest import uncategorised

    cfg = load_config()
    if not cfg.flags.get("category_suggestions"):
        print("error: flag category_suggestions is off in config.yaml")
        return 2
    store = CsvFinanceStore(cfg.finance_dir)
    return _queue_suggestions(cfg, store, uncategorised(store), [])


def _statements(_args: argparse.Namespace) -> int:
    cfg = load_config()
    for f in list_statement_files(cfg, CsvFinanceStore(cfg.finance_dir)):
        print(f"{'imported' if f.imported else 'new':9}{f.name}")
    return 0


def _private_adapter(cfg):
    """The private model chain when routing is on; raises ConfigError if it cannot be built."""
    if not cfg.flags.get("private_routing"):
        return None
    if not cfg.private_models:
        raise ConfigError("flag private_routing is on but private_models is empty in config.yaml")
    try:
        return build_private_adapter(cfg)
    except AdapterError as e:
        raise ConfigError(f"private model: {e}") from e


def _chat(args: argparse.Namespace) -> int:
    load_env()
    cfg = load_config()
    which = "local" if args.local else "default"
    if which not in cfg.models:
        print(f"error: no models.{which} in config.yaml")
        return 2
    try:
        private = _private_adapter(cfg)
    except ConfigError as e:
        print(f"error: {e}")
        return 2
    chat_loop(cfg, build_adapter(cfg.models[which]), resume=args.resume, private_adapter=private)
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
    try:
        private = _private_adapter(cfg)
    except ConfigError as e:
        print(f"error: {e}")
        return 2
    app = create_app(
        cfg,
        lambda: build_adapter(model),
        start_scheduler=True,
        private_factory=(lambda: build_private_adapter(cfg)) if private else None,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


def _intake(args: argparse.Namespace) -> int:
    import shutil
    import tempfile

    from server.intake.runner import run_documents_job, run_memory_job

    load_env()
    cfg = load_config()
    if not cfg.flags.get("intake"):
        print("error: flag intake is off in config.yaml")
        return 2
    if "default" not in cfg.models:
        print("error: no models.default in config.yaml")
        return 2
    if not args.files and not args.memory:
        print("error: give document files, or --memory FILE")
        return 2
    adapter = build_adapter(cfg.models["default"])
    db = Db(cfg.db_path)
    if db.running_intake_job():
        print("error: another intake job is running")
        return 1
    jobs = []
    if args.files:
        job = db.new_intake_job("documents", datetime.now())
        tmp = Path(tempfile.mkdtemp(prefix="ka-intake-"))
        copies = []
        for f in args.files:  # the runner deletes its inputs, so never hand it the originals
            copies.append(Path(shutil.copy(f, tmp / Path(f).name)))
        run_documents_job(job, copies, cfg, adapter)
        jobs.append(job)
    if args.memory:
        job = db.new_intake_job("memory", datetime.now())
        run_memory_job(job, Path(args.memory).read_text(), args.source, cfg, adapter)
        jobs.append(job)
    code = 0
    for job in jobs:
        got = db.get_intake_job(job)
        if got.status == "failed":
            print(f"failed: {got.message}")
            code = 1
            continue
        print(f"queued {got.result['cards']} card(s)")
        for w in got.result["warnings"]:
            print(f"  warning: {w}")
        for s in got.result["skipped"]:
            print(f"  skipped: {s}")
    return code


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
    try:
        n = extract_memories(
            day,
            Db(cfg.db_path),
            load_data(cfg.data_repo),
            build_adapter(cfg.models[which]),
            datetime.now(),
            private_adapter=_private_adapter(cfg),
        )
    except (AdapterError, ConfigError) as e:
        print(f"error: {e}")
        return 1
    print(f"queued {n} item(s) from {day}")
    return 0


def _pending(args: argparse.Namespace) -> int:
    cfg = load_config()
    db = Db(cfg.db_path)
    if args.action is None:
        old = {e.id: e.text for e in load_data(cfg.data_repo).memory.entries}
        for item in db.list_pending():
            p = item.payload
            if item.kind == "bundle":
                print(
                    f"{item.id:>3}  [{p['section']}] {p['title']}"
                    + (f"  BLOCKED: {p['blocked']}" if p.get("blocked") else "")
                )
                for it in p["items"]:
                    print(f"       - {it['label']}  ({it['detail']})")
                continue
            print(f"{item.id:>3}  [{p['type']}] {p['text']}")
            if p.get("replaces"):
                print(f"     replaces {p['replaces']}: {old.get(p['replaces'], '?')}")
        return 0
    try:
        item = db.get_pending(args.id)
        bundle = item is not None and item.kind == "bundle"
        if args.action == "approve":
            if bundle:
                print(
                    approve_bundle(
                        args.id,
                        None,
                        cfg.data_repo,
                        db,
                        date.today(),
                        CsvFinanceStore(cfg.finance_dir),
                    )
                )
            else:
                print(approve_pending(args.id, cfg.data_repo, db, date.today()))
        else:
            reject_bundle(args.id, db) if bundle else reject_pending(args.id, db)
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
    sub.add_parser(
        "suggest", help="queue category suggestions for uncategorised rows"
    ).set_defaults(func=_suggest)
    chat = sub.add_parser("chat", help="talk to Ka in the terminal")
    chat.add_argument("--local", action="store_true", help="use the local Ollama model only")
    chat.add_argument("--resume", help="continue a saved conversation id")
    chat.set_defaults(func=_chat)
    serve = sub.add_parser("serve", help="run the web UI on localhost")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)
    intake = sub.add_parser("intake", help="read a resume or pasted memory into pending cards")
    intake.add_argument("files", nargs="*", help="resume and other documents")
    intake.add_argument("--memory", help="a text file with another assistant's memory export")
    intake.add_argument("--source", default="assistant", help="name of that assistant")
    intake.set_defaults(func=_intake)
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
