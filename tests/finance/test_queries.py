from datetime import date
from decimal import Decimal

from server.finance.models import Transaction
from server.finance.queries import find_transactions, sum_rows, summarise


def tx(n, amount, tag, category="", desc="Shop", day=5):
    return Transaction(
        id=f"s-{n:03d}",
        account="A-01",
        statement_id="s",
        date=date(2031, 4, day),
        type="Point of sale purchase",
        description=desc,
        amount=Decimal(amount),
        balance=Decimal(0),
        tag=tag,
        category=category,
    )


def test_summary_nets_corrections_excludes_transfers_and_reports_no_data():
    rows = [
        tx(1, "-10.00", "purchase", "dining"),
        tx(2, "10.00", "refund", "dining"),
        tx(3, "-50.00", "own_transfer"),
        tx(4, "100.00", "income"),
        tx(5, "-30.00", "debt_payment"),
        tx(6, "-4.50", "purchase"),
    ]
    s = summarise(rows, date(2031, 4, 1), date(2031, 4, 30))
    assert s.spending == Decimal("4.50")
    assert s.by_category == {"dining": Decimal("0.00"), "uncategorised": Decimal("4.50")}
    assert (s.income, s.debt_payments) == (Decimal("100.00"), Decimal("30.00"))
    empty = summarise(rows, date(2019, 1, 1), date(2019, 12, 31))
    assert empty.has_data is False and empty.spending is None and empty.by_category == {}


def test_search_ignores_case_and_spaces_and_sum_is_exact():
    rows = [tx(1, "-0.10", "purchase", desc="Apos TimHortons#22"), tx(2, "-0.20", "purchase")]
    assert [r.id for r in find_transactions(rows, "tim hortons")] == ["s-001"]
    assert [r.id for r in find_transactions(rows, "TIMHORTONS")] == ["s-001"]
    assert sum_rows(rows, ["s-001", "s-002", "s-999"]) == (Decimal("-0.30"), ["s-999"])


def test_sum_rows_counts_a_repeated_id_once():
    rows = [tx(1, "-10.00", "purchase"), tx(2, "-5.00", "purchase")]
    total, missing = sum_rows(rows, ["s-001", "s-001", "s-002", "s-009"])
    assert total == Decimal("-15.00") and missing == ["s-009"]


def test_sum_tool_counts_unique_ids(ctx):
    from server.agent.tools import run_tool

    rows = [tx(1, "-10.00", "purchase"), tx(2, "-5.00", "purchase")]
    ctx.store = type("Store", (), {"transactions": lambda self: rows})()
    out = run_tool("finance_sum_transactions", {"ids": ["s-001", "s-001", "s-002"]}, ctx)
    assert out["count"] == 2 and out["total"] == "-15.00"
