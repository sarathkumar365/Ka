from datetime import UTC, date, datetime
from decimal import Decimal

from server.finance.models import StatementRecord, Transaction
from server.finance.store import CsvFinanceStore

STATEMENT = StatementRecord(
    statement_id="s1",
    account="A-01",
    period_start=date(2031, 3, 24),
    period_end=date(2031, 4, 23),
    opening_balance=Decimal("500.00"),
    total_withdrawals=Decimal("1.00"),
    total_deposits=Decimal("0.00"),
    closing_balance=Decimal("499.00"),
    file_name="a.pdf",
    imported_at=datetime(2031, 4, 24, tzinfo=UTC),
)


def tx(n, desc='VISA, "Example" Financial'):
    return Transaction(
        id=f"s1-{n:03d}",
        account="A-01",
        statement_id="s1",
        date=date(2031, 3, 25),
        type="Point of sale purchase",
        description=desc,
        amount=Decimal("-1250.00"),
        balance=Decimal("-0.50"),
        tag="purchase",
    )


def test_round_trips_exact_values_and_skips_duplicate_imports(tmp_path):
    store = CsvFinanceStore(tmp_path)
    assert store.add_import(STATEMENT, [tx(1), tx(2)]) == 2
    reloaded = CsvFinanceStore(tmp_path)
    assert reloaded.transactions() == [tx(1), tx(2)]  # commas, quotes, Decimal, empty fields
    assert reloaded.statements() == [STATEMENT]
    assert reloaded.add_import(STATEMENT, [tx(1), tx(2)]) == 0
    assert len(reloaded.statements()) == 1
