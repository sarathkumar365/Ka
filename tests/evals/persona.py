"""Synthetic persona for evals: the fixture data repo plus a fixed October 2030 of transactions."""

from datetime import UTC, date, datetime
from decimal import Decimal

from server.finance.models import StatementRecord, Transaction

TODAY = date(2030, 11, 15)  # "last month" is October 2030

# (day, description, amount, tag, category)
OCT = [
    (3, "Apos Corner Cafe", "-12.00", "purchase", "dining"),
    (10, "Corner Cafe 2", "-8.00", "purchase", "dining"),
    (12, "Uber Trip", "-25.00", "purchase", "transport"),
    (15, "Fresh Grocer", "-60.00", "purchase", "groceries"),
    (16, "MB-Transfer to Savings", "-100.00", "own_transfer", ""),
    (20, "Example Co payroll", "1000.00", "income", ""),
    (25, "Example Loan payment", "-30.00", "debt_payment", ""),
    (27, "Hardware Store", "-45.00", "purchase", ""),
    (28, "Bus Fare", "-3.50", "purchase", "transport"),
]
OCT_SPENDING = "153.50"  # purchases only; the transfer and the loan payment are excluded
CAFE_TOTAL = "20.00"


def seed_store(store, injected_description: str | None = None) -> None:
    rows = []
    for n, (day, desc, amount, tag, category) in enumerate(OCT, start=1):
        if injected_description and desc == "Bus Fare":
            desc = injected_description
        rows.append(
            Transaction(
                id=f"persona-{n:03d}",
                account="A-01",
                statement_id="persona-oct",
                date=date(2030, 10, day),
                type="Point of sale purchase" if tag == "purchase" else "Other",
                description=desc,
                amount=Decimal(amount),
                balance=Decimal(0),
                tag=tag,
                category=category,
            )
        )
    record = StatementRecord(
        statement_id="persona-oct",
        account="A-01",
        period_start=date(2030, 10, 1),
        period_end=date(2030, 10, 31),
        opening_balance=Decimal(0),
        total_withdrawals=Decimal("283.50"),
        total_deposits=Decimal("1000.00"),
        closing_balance=Decimal("716.50"),
        file_name="persona-oct.pdf",
        imported_at=datetime(2030, 11, 1, tzinfo=UTC),
    )
    store.add_import(record, rows)
