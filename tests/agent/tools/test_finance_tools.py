from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from server.agent.tools import ToolError, run_tool
from server.finance.models import StatementRecord, Transaction


def seed(ctx, file_name="a.pdf"):
    rows = [
        Transaction(
            id=f"s-{n:03d}",
            account="A-01",
            statement_id="s",
            date=date(2031, 4, n),
            type="Point of sale purchase",
            description="Apos Corner Cafe",
            amount=Decimal("-1.50"),
            balance=Decimal(0),
            tag="purchase",
            category="dining",
        )
        for n in (1, 2, 3)
    ]
    record = StatementRecord(
        statement_id="s",
        account="A-01",
        period_start=date(2031, 3, 24),
        period_end=date(2031, 4, 23),
        opening_balance=Decimal(0),
        total_withdrawals=Decimal("4.50"),
        total_deposits=Decimal(0),
        closing_balance=Decimal("-4.50"),
        file_name=file_name,
        imported_at=datetime(2031, 4, 24, tzinfo=UTC),
    )
    ctx.store.add_import(record, rows)


def test_tools_return_strings_limit_rows_and_mark_imported_files(ctx):
    seed(ctx)
    found = run_tool("search_transactions", {"limit": 2}, ctx)
    assert (len(found["rows"]), found["total_matches"], found["truncated"]) == (2, 3, True)
    assert found["rows"][0]["amount"] == "-1.50"
    assert run_tool("sum_transactions", {"ids": ["s-001", "s-002"]}, ctx)["total"] == "-3.00"
    summary = run_tool("finance_summary", {"start": "2031-04-01", "end": "2031-04-30"}, ctx)
    assert summary["spending"] == "4.50"

    statements = ctx.config.statements_dir
    statements.mkdir(parents=True)
    (statements / "a.pdf").write_bytes(b"x")
    (statements / "b.pdf").write_bytes(b"x")
    files = run_tool("list_statements", {}, ctx)["files"]
    assert files == [{"name": "a.pdf", "imported": True}, {"name": "b.pdf", "imported": False}]


def test_finance_summary_rejects_start_after_end(ctx):
    with pytest.raises(ToolError, match="start"):
        run_tool("finance_summary", {"start": "2031-05-01", "end": "2031-04-01"}, ctx)


def test_finance_coverage_lists_months_and_statements(ctx):
    seed(ctx)
    out = run_tool("finance_coverage", {}, ctx)
    assert out["has_data"] and out["rows"] == 3
    assert (out["data_from"], out["data_to"]) == ("2031-04-01", "2031-04-03")
    assert out["months"] == [{"month": "2031-04", "rows": 3}]
    assert out["statements"][0]["period_start"] == "2031-03-24"
    empty = run_tool(
        "finance_coverage",
        {},
        ctx.__class__(config=ctx.config, store=type(ctx.store)(ctx.store.folder / "x")),
    )
    assert empty["has_data"] is False and empty["months"] == []
