"""Pure read-side maths over stored transactions. Money stays Decimal."""

from datetime import date
from decimal import Decimal

from server.integrations.data_repo.schemas.common import KaModel

from .models import Transaction
from .tagging import norm

SPENDING_TAGS = {"purchase", "fee", "refund", "nsf_return"}
ZERO = Decimal(0)


class Summary(KaModel):
    start: date
    end: date
    has_data: bool
    rows: int
    data_from: date | None = None
    data_to: date | None = None
    spending: Decimal | None = None  # positive; own transfers and borrowing are not spending
    by_category: dict[str, Decimal] = {}
    income: Decimal | None = None
    debt_payments: Decimal | None = None  # positive
    borrowing: Decimal | None = None


def _total(rows: list[Transaction], tags: set[str]) -> Decimal:
    return sum((r.amount for r in rows if r.tag in tags), ZERO)


def summarise(rows: list[Transaction], start: date, end: date) -> Summary:
    inside = [r for r in rows if start <= r.date <= end]
    if not inside:
        return Summary(start=start, end=end, has_data=False, rows=0)
    by_category: dict[str, Decimal] = {}
    for r in inside:
        if r.tag in SPENDING_TAGS:
            key = r.category or "uncategorised"
            by_category[key] = by_category.get(key, ZERO) - r.amount
    return Summary(
        start=start,
        end=end,
        has_data=True,
        rows=len(inside),
        data_from=min(r.date for r in inside),
        data_to=max(r.date for r in inside),
        spending=-_total(inside, SPENDING_TAGS),
        by_category=by_category,
        income=_total(inside, {"income"}),
        debt_payments=-_total(inside, {"debt_payment"}),
        borrowing=_total(inside, {"borrowing"}),
    )


def find_transactions(
    rows: list[Transaction],
    query: str = "",
    start: date | None = None,
    end: date | None = None,
    tag: str | None = None,
    category: str | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
) -> list[Transaction]:
    needle = norm(query)
    out = []
    for r in rows:
        if needle and needle not in norm(r.description) and needle not in norm(r.type):
            continue
        if (start and r.date < start) or (end and r.date > end):
            continue
        if tag and r.tag != tag:
            continue
        if category is not None and r.category != category:
            continue
        if min_amount is not None and abs(r.amount) < min_amount:
            continue
        if max_amount is not None and abs(r.amount) > max_amount:
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r.date, r.id))


def sum_rows(rows: list[Transaction], ids: list[str]) -> tuple[Decimal, list[str]]:
    by_id = {r.id: r for r in rows}
    unique = list(dict.fromkeys(ids))
    missing = [i for i in unique if i not in by_id]
    return sum((by_id[i].amount for i in unique if i in by_id), ZERO), missing
