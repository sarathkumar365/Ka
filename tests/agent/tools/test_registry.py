from decimal import Decimal

import pytest

from server.agent.tools import registry
from server.agent.tools.registry import ToolError, run_tool, tool
from server.integrations.data_repo.schemas.common import KaModel


class Args(KaModel):
    amount: Decimal


def test_validates_args_serialises_money_and_rejects_unknown(monkeypatch):
    monkeypatch.setattr(registry, "REGISTRY", {})

    @tool("add", "adds", Args)
    def add(args, ctx):
        return {"total": args.amount + Decimal("0.20")}

    assert run_tool("add", {"amount": "0.10"}, None)["total"] == "0.30"
    with pytest.raises(ToolError, match="amount"):
        run_tool("add", {"amount": "x"}, None)
    with pytest.raises(ToolError, match="unknown tool"):
        run_tool("nope", {}, None)
