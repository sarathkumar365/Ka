from datetime import date
from decimal import Decimal

import pytest

from server.agent.tools import PendingWrite, ToolError, run_tool
from server.integrations.data_repo.loader import load_data
from tests.conftest import git
from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement


def commits(ctx):
    return int(git(ctx.config.data_repo, "rev-list", "--count", "HEAD"))


def test_propose_change_writes_only_on_apply(ctx):
    before = (commits(ctx), (ctx.config.data_repo / "accounts.yaml").read_text())
    pending = run_tool(
        "propose_change",
        {"target": "account", "op": "update", "key": "A-01", "fields": {"label": "Main"}},
        ctx,
    )
    assert isinstance(pending, PendingWrite) and "Main" in pending.diff
    assert (commits(ctx), (ctx.config.data_repo / "accounts.yaml").read_text()) == before
    pending.apply()
    assert commits(ctx) == before[0] + 1
    assert load_data(ctx.config.data_repo).accounts.accounts[0].label == "Main"


def test_remember_saves_immediately(ctx):
    ctx.today = lambda: date(2031, 4, 1)
    out = run_tool("remember", {"text": "Prefers remote roles", "type": "preference"}, ctx)
    assert out["id"] == "M-0002"
    entry = load_data(ctx.config.data_repo).memory.entries[-1]
    assert (entry.text, entry.type, entry.created) == (
        "Prefers remote roles",
        "preference",
        "2031-04-01",
    )
    assert git(ctx.config.data_repo, "log", "-1", "--format=%s") == "data: add memory M-0002"


def test_import_statement_approval_and_refusals(ctx):
    folder = ctx.config.statements_dir
    folder.mkdir(parents=True)
    rows = [
        SpecRow(date(2031, 3, 25), "Point of sale purchase", "Apos Corner Cafe", Decimal("-4.50")),
        SpecRow(date(2031, 3, 26), "Payroll dep.", "Example Co Ltd.", Decimal("1250.00")),
    ]
    build_statement(folder / "s.pdf", StatementSpec(rows=rows))
    pending = run_tool("import_statement", {"file_name": "s.pdf"}, ctx)
    assert "2 rows" in pending.summary and ctx.store.transactions() == []
    pending.apply()
    assert len(ctx.store.transactions()) == 2
    with pytest.raises(ToolError, match="already imported"):
        run_tool("import_statement", {"file_name": "s.pdf"}, ctx)
    for bad in ("../s.pdf", "notes.txt", "missing.pdf"):
        with pytest.raises(ToolError):
            run_tool("import_statement", {"file_name": bad}, ctx)
    build_statement(folder / "bad.pdf", StatementSpec(rows=rows, closing_balance=Decimal("1.00")))
    with pytest.raises(ToolError, match="opening_closing"):
        run_tool("import_statement", {"file_name": "bad.pdf"}, ctx)
