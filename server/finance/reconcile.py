"""Turns raw rows into signed ledger rows and runs the checks that guard every import."""

from datetime import date
from decimal import Decimal

from .models import CheckFailure, LedgerRow, ParsedStatement


def _full_date(month: int, day: int, start: date, end: date) -> date | None:
    for year in sorted({start.year, end.year}):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if start <= d <= end:
            return d
    return None


def reconcile(parsed: ParsedStatement) -> tuple[list[LedgerRow], list[CheckFailure]]:
    s = parsed.summary
    rows: list[LedgerRow] = []
    row_failures: list[CheckFailure] = []
    previous = s.opening_balance
    for r in parsed.rows:
        delta = r.balance - previous
        signed = -r.amount if delta < 0 else r.amount
        if abs(delta) != r.amount:
            row_failures.append(
                CheckFailure(
                    check="row_balance",
                    row_number=r.row_number,
                    message=f"balance moved {delta} but amount is {r.amount}",
                )
            )
        if (r.column == "withdrawn" and delta >= 0) or (r.column == "deposited" and delta <= 0):
            row_failures.append(
                CheckFailure(
                    check="column_direction",
                    row_number=r.row_number,
                    message=f"{r.column} column but balance moved {delta}",
                )
            )
        d = _full_date(r.month, r.day, s.period_start, s.period_end)
        if d is None:
            row_failures.append(
                CheckFailure(
                    check="date_out_of_period",
                    row_number=r.row_number,
                    message=f"{r.month}/{r.day} is outside {s.period_start}..{s.period_end}",
                )
            )
            d = s.period_end
        rows.append(
            LedgerRow(
                row_number=r.row_number,
                date=d,
                type_text=r.type_text,
                description=r.description,
                amount=signed,
                balance=r.balance,
            )
        )
        previous = r.balance

    failures = sorted(row_failures, key=lambda f: f.row_number or 0)
    out = sum((-x.amount for x in rows if x.amount < 0), Decimal(0))
    inn = sum((x.amount for x in rows if x.amount > 0), Decimal(0))
    if out != s.total_withdrawals or inn != s.total_deposits:
        failures.append(
            CheckFailure(
                check="summary_totals",
                row_number=None,
                message=(
                    f"rows give withdrawals {out} / deposits {inn}, "
                    f"summary says {s.total_withdrawals} / {s.total_deposits}"
                ),
            )
        )
    last = rows[-1].balance if rows else s.opening_balance
    if s.opening_balance + s.total_deposits - s.total_withdrawals != s.closing_balance or (
        last != s.closing_balance
    ):
        failures.append(
            CheckFailure(
                check="opening_closing",
                row_number=None,
                message=(
                    f"opening {s.opening_balance} + deposits {s.total_deposits} - withdrawals "
                    f"{s.total_withdrawals} vs closing {s.closing_balance}, last row balance {last}"
                ),
            )
        )
    return rows, failures
