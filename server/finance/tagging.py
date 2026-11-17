"""Tags and categorises ledger rows by rules, and links corrections to the charge they undo."""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from ruamel.yaml import YAML

from server.integrations.data_repo.loader import KaData
from server.integrations.data_repo.schemas.rules import TransactionTypeRule, TransactionTypesFile

from .models import LedgerRow, Transaction

DEFAULTS_DIR = Path(__file__).parent / "defaults"
NETTING_WINDOW = timedelta(days=60)
SPENDING_TAGS = {"purchase", "refund", "nsf_return"}


@dataclass
class TagResult:
    transactions: list[Transaction]
    unknown_types: list[str] = field(default_factory=list)
    unknown_merchants: list[str] = field(default_factory=list)
    unlinked: list[str] = field(default_factory=list)


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s.casefold())


def load_type_rules(data: KaData, bank: str) -> list[TransactionTypeRule]:
    raw = YAML(typ="safe").load((DEFAULTS_DIR / f"{bank}_types.yaml").read_text())
    rules = {norm(r.type_text): r for r in TransactionTypesFile(**raw).types if r.bank == bank}
    for r in data.transaction_types.types:
        if r.bank == bank:
            rules[norm(r.type_text)] = r
    return list(rules.values())


def _own_account_tag(
    description: str, amount, data: KaData, skip_account: str, rule: TransactionTypeRule | None
) -> str | None:
    text = norm(description)
    for a in data.accounts.accounts:
        if not a.mine or a.id == skip_account:
            continue
        if any(norm(m) in text for m in a.match):
            if a.kind in ("chequing", "savings", "investment"):
                return "own_transfer"
            if amount < 0:
                return "debt_payment"
            # money in from a card or loan is new borrowing only when the bank says so (Loans)
            return "borrowing" if rule and rule.tag == "borrowing" else "refund"
    return None


def _find_original(
    row: Transaction, pool: list[Transaction], taken: set[str]
) -> Transaction | None:
    candidates = [
        t
        for t in pool
        if t.account == row.account
        and norm(t.description) == norm(row.description)
        and t.amount == -row.amount
        and timedelta(0) <= row.date - t.date <= NETTING_WINDOW
        and t.id not in taken
    ]
    return max(candidates, key=lambda t: (t.date, t.id), default=None)


def tag_rows(
    rows: list[LedgerRow],
    statement_id: str,
    account_id: str,
    data: KaData,
    existing: list[Transaction],
    bank: str = "scotiabank",
) -> TagResult:
    type_rules = {norm(r.type_text): r for r in load_type_rules(data, bank)}
    result = TagResult(transactions=[])
    taken = {t.linked_id for t in existing if t.linked_id}
    for row in rows:
        rule = type_rules.get(norm(row.type_text))
        own = None
        if rule and rule.nets_against_original:
            tag = rule.tag
        else:
            own = _own_account_tag(row.description, row.amount, data, account_id, rule)
            if own:
                tag = own
            elif rule:
                tag = rule.tag
            else:
                tag = "purchase" if row.amount < 0 else "income"
                if row.type_text not in result.unknown_types:
                    result.unknown_types.append(row.type_text)
        category = ""
        if not own:
            text = norm(row.description)
            category = next(
                (m.category for m in data.merchant_rules.rules if norm(m.match) in text), ""
            )
        tx = Transaction(
            id=f"{statement_id}-{row.row_number:03d}",
            account=account_id,
            statement_id=statement_id,
            date=row.date,
            type=row.type_text,
            description=row.description,
            amount=row.amount,
            balance=row.balance,
            tag=tag,
            category=category,
        )
        if rule and rule.nets_against_original:
            original = _find_original(tx, existing + result.transactions, taken)
            if original:
                tx.linked_id = original.id
                taken.add(original.id)
            else:
                result.unlinked.append(tx.id)
        if (
            not own
            and not category
            and tag in SPENDING_TAGS
            and tx.description not in result.unknown_merchants
        ):
            result.unknown_merchants.append(tx.description)
        result.transactions.append(tx)
    return result
