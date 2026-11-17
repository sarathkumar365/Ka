from datetime import date
from decimal import Decimal

from server.finance.parser import parse_statement
from server.finance.reconcile import reconcile
from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement


def run(tmp_path, rows, **spec):
    p = tmp_path / "s.pdf"
    build_statement(p, StatementSpec(rows=rows, **spec))
    return reconcile(parse_statement(p))


def r(y, m, d, amount, **kw):
    return SpecRow(
        date(y, m, d), "Point of sale purchase", "Apos Corner Cafe", Decimal(amount), **kw
    )


def test_clean_statement_signs_amounts_and_places_dates_across_new_year(tmp_path):
    rows = [r(2031, 12, 30, "-4.50"), r(2032, 1, 5, "100.00")]
    ledger, failures = run(
        tmp_path, rows, period_start=date(2031, 12, 24), period_end=date(2032, 1, 23)
    )
    assert failures == []
    assert [(x.date, x.amount) for x in ledger] == [
        (date(2031, 12, 30), Decimal("-4.50")),
        (date(2032, 1, 5), Decimal("100.00")),
    ]


def test_each_check_names_what_failed(tmp_path):
    rows = [r(2031, 3, 25, "-4.50"), r(2031, 3, 26, "-1.00", balance=Decimal("400.00"))]
    _, failures = run(tmp_path, rows)
    assert [(f.check, f.row_number) for f in failures if f.check == "row_balance"] == [
        ("row_balance", 2)
    ]

    _, failures = run(tmp_path, rows[:1], totals=(Decimal("9.99"), Decimal(0)))
    assert [f.check for f in failures] == ["summary_totals", "opening_closing"]

    _, failures = run(tmp_path, rows[:1], closing_balance=Decimal("1.00"))
    assert [f.check for f in failures] == ["opening_closing"]

    _, failures = run(tmp_path, [r(2031, 3, 25, "-4.50", column="deposited")])
    assert "column_direction" in [f.check for f in failures]
