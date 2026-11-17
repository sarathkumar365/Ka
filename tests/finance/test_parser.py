from datetime import date
from decimal import Decimal

import pytest

from server.finance.parser import StatementFormatError, parse_statement
from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement


def row(day, type_text, desc, amount, **kw):
    return SpecRow(date(2031, 3, day), type_text, desc, Decimal(amount), **kw)


def test_parses_summary_rows_columns_and_awkward_descriptions(tmp_path):
    rows = [
        row(25, "Point of sale purchase", "Apos Corner Cafe", "-4.50"),
        row(26, "Payroll dep.", "Example Co Ltd.", "1250.00"),
        row(
            27, "Point of sale purchase", None, "-1700.00"
        ),  # no description; balance goes negative
        row(28, "Point of sale purchase", "Opos 5.00 Railway +1415 CAUS", "-7.33"),
    ]
    p = tmp_path / "s.pdf"
    build_statement(p, StatementSpec(rows=rows, rows_per_page=3))
    parsed = parse_statement(p)
    s = parsed.summary
    assert (s.account_number, s.period_start, s.period_end) == (
        "111112222233",
        date(2031, 3, 24),
        date(2031, 4, 23),
    )
    assert (s.opening_balance, s.total_withdrawals, s.total_deposits) == (
        Decimal("500.00"),
        Decimal("1711.83"),
        Decimal("1250.00"),
    )
    assert [r.row_number for r in parsed.rows] == [1, 2, 3, 4]  # crosses a page break
    assert parsed.rows[1].amount == Decimal("1250.00") and parsed.rows[1].column == "deposited"
    assert parsed.rows[1].balance == Decimal("1745.50")
    assert parsed.rows[2].description == "" and parsed.rows[2].balance == Decimal("45.50")
    assert parsed.rows[3].description == "Opos 5.00 Railway +1415 CAUS"
    assert parsed.rows[3].amount == Decimal("7.33")


def test_rejects_scanned_and_other_bank_pdfs(tmp_path):
    p = tmp_path / "a.pdf"
    build_statement(p, StatementSpec(text_layer=False))
    with pytest.raises(StatementFormatError, match="no text layer"):
        parse_statement(p)
    build_statement(p, StatementSpec(scotiabank=False))
    with pytest.raises(StatementFormatError, match="not a Scotiabank"):
        parse_statement(p)
