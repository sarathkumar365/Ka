"""The import flow: parse, reconcile, tag, preview, then write only after approval."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from server.integrations.data_repo.loader import KaData

from .models import CheckFailure, StatementRecord, Transaction
from .parser import parse_statement
from .reconcile import reconcile
from .store import FinanceStore
from .tagging import norm, tag_rows


class ImportFailed(Exception):
    pass


@dataclass
class ImportPreview:
    statement: StatementRecord
    transactions: list[Transaction]
    failures: list[CheckFailure]
    unknown_types: list[str]
    unknown_merchants: list[str]
    unlinked: list[str]
    already_imported: bool


def _find_account(data: KaData, number: str):
    mine = [a for a in data.accounts.accounts if a.mine]
    for a in mine:  # full number first: last4 alone can collide across accounts
        if number in [norm(m) for m in a.match]:
            return a
    for a in mine:
        if a.last4 == number[-4:]:
            return a
    raise ImportFailed(f"account ending {number[-4:]} is not in accounts.yaml; add it and retry")


def prepare_import(pdf: Path, data: KaData, store: FinanceStore) -> ImportPreview:
    parsed = parse_statement(pdf)
    s = parsed.summary
    account = _find_account(data, s.account_number)
    statement_id = f"{s.bank}-{account.kind}-{s.account_number[-4:]}-{s.period_end:%Y-%m}"
    rows, failures = reconcile(parsed)
    tagged = tag_rows(rows, statement_id, account.id, data, store.transactions(), bank=s.bank)
    record = StatementRecord(
        statement_id=statement_id,
        account=account.id,
        period_start=s.period_start,
        period_end=s.period_end,
        opening_balance=s.opening_balance,
        total_withdrawals=s.total_withdrawals,
        total_deposits=s.total_deposits,
        closing_balance=s.closing_balance,
        file_name=parsed.file_name,
        imported_at=datetime.now(UTC),
    )
    return ImportPreview(
        statement=record,
        transactions=tagged.transactions,
        failures=failures,
        unknown_types=tagged.unknown_types,
        unknown_merchants=tagged.unknown_merchants,
        unlinked=tagged.unlinked,
        already_imported=statement_id in {x.statement_id for x in store.statements()},
    )


def commit_import(preview: ImportPreview, store: FinanceStore) -> int:
    if preview.failures:
        raise ImportFailed("checks failed; nothing written")
    if preview.already_imported:
        raise ImportFailed(f"already imported: {preview.statement.statement_id}")
    return store.add_import(preview.statement, preview.transactions)
