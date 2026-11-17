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


def test_reapply_fills_only_empty(ctx):
    from server.finance.tagging import reapply_rules
    from server.integrations.data_repo.loader import load_data

    store = CsvFinanceStore(ctx.store.folder)
    rows = [
        tx(1, "CORNER CAFE TORONTO").model_copy(update={"tag": "purchase"}),
        tx(2, "CORNER CAFE NORTH").model_copy(update={"tag": "purchase", "category": "groceries"}),
        tx(3, "UNKNOWN PLACE").model_copy(update={"tag": "purchase"}),
    ]
    store.add_import(STATEMENT, rows)
    assert reapply_rules(store, load_data(ctx.config.data_repo)) == 1
    got = {t.id: t.category for t in store.transactions()}
    assert got == {"s1-001": "dining", "s1-002": "groceries", "s1-003": ""}
    assert reapply_rules(store, load_data(ctx.config.data_repo)) == 0


def test_concurrent_import_and_recategorise_keep_all_rows(tmp_path, monkeypatch):
    import threading
    import time

    store = CsvFinanceStore(tmp_path / "fin")
    store.add_import(STATEMENT, [tx(1, "CORNER CAFE").model_copy(update={"tag": "purchase"})])
    real_read = CsvFinanceStore._read

    def slow_read(self, path, model):
        rows = real_read(self, path, model)
        time.sleep(0.05)  # widen the read-then-write window
        return rows

    monkeypatch.setattr(CsvFinanceStore, "_read", slow_read)
    s2 = STATEMENT.model_copy(update={"statement_id": "s2"})
    new = [tx(n).model_copy(update={"id": f"s2-{n:03d}", "statement_id": "s2"}) for n in range(5)]
    a = threading.Thread(target=lambda: store.update_categories({"s1-001": "dining"}))
    b = threading.Thread(target=lambda: CsvFinanceStore(tmp_path / "fin").add_import(s2, new))
    a.start()
    b.start()
    a.join()
    b.join()
    rows = {t.id: t.category for t in store.transactions()}
    assert len(rows) == 6 and rows["s1-001"] == "dining"
