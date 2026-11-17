import argparse
import sys
from pathlib import Path

from server.config import ConfigError, load_config
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.finance.statements import list_statement_files
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import DataRepoError, load_data

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ka")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate the data repo").set_defaults(func=_check)
    imp = sub.add_parser("import", help="import a statement PDF")
    imp.add_argument("path")
    imp.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    imp.set_defaults(func=_import)
    sub.add_parser("statements", help="list statement PDFs").set_defaults(func=_statements)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DataRepoError, ImportFailed, StatementFormatError) as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
