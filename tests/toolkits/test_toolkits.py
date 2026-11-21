from datetime import datetime

import pytest

from server.agent.adapters import FakeAdapter, Reply, ToolCall
from server.agent.loop import run_turn
from server.agent.tools import REGISTRY, registry
from server.agent.tools.registry import tool
from server.integrations.data_repo.schemas.common import KaModel
from server.store.db import Db
from server.toolkits import base
from server.toolkits.base import Manifest, manifests

NOW = lambda: datetime(2031, 4, 5, 12, 0)


class NoArgs(KaModel):
    pass


def call(name, args="{}", id="c1"):
    return ToolCall(id, name, args)


def ask_in(ctx, replies, conv=None, flags=None):
    if flags is not None:
        ctx.config = ctx.config.model_copy(update={"flags": flags})
    ctx.db = ctx.db or Db(":memory:", "avery")
    cid = conv or ctx.db.new_conversation(NOW())
    adapter = FakeAdapter(replies)
    run_turn("q", conv_id=cid, db=ctx.db, adapter=adapter, ctx=ctx, approve=lambda p: True, now=NOW)
    return cid, ctx.db.messages(cid), adapter


def names(adapter, i=0):
    return {t["function"]["name"] for t in adapter.tools[i]}


def test_prefix_and_approval_label_are_enforced():
    with pytest.raises(ValueError, match="prefix"):
        tool("search_x", "d", NoArgs, toolkit="finance")
    with pytest.raises(ValueError, match="risky"):
        tool("finance_y", "d", NoArgs, toolkit="finance", approval=True)


def test_chat_starts_with_core_tools_only(ctx):
    _, _, adapter = ask_in(ctx, [Reply(text="hi")])
    assert "load_toolkit" in names(adapter) and "finance_summary" not in names(adapter)


def test_unloaded_tool_is_refused(ctx):
    _, msgs, _ = ask_in(ctx, [Reply(tool_calls=[call("finance_summary")]), Reply(text="x")])
    assert [m["content"] for m in msgs if m["role"] == "tool"] == ["error: unknown tool: finance_summary"]


def test_loaded_toolkit_persists_for_the_chat(ctx):
    cid, msgs, _ = ask_in(ctx, [Reply(tool_calls=[call("load_toolkit", '{"name": "finance"}')]), Reply(text="ok")])
    assert "finance_coverage" in next(m for m in msgs if m["role"] == "tool")["content"]  # instructions came back
    _, _, adapter = ask_in(ctx, [Reply(text="again")], conv=cid)
    assert "finance_summary" in names(adapter)
    assert ctx.db.is_private(cid)  # finance manifest is private


def test_flag_off_hides_loaded_toolkit(ctx, monkeypatch):
    kits = {**manifests(), "kit": Manifest(name="kit", description="test kit", flag="movies")}
    monkeypatch.setattr(base, "manifests", lambda: kits)
    monkeypatch.setattr(registry, "REGISTRY", dict(REGISTRY))
    monkeypatch.setattr("server.agent.tools.REGISTRY", registry.REGISTRY)
    tool("kit_ping", "ping", NoArgs, toolkit="kit")(lambda a, c: "pong")
    cid, _, _ = ask_in(ctx, [Reply(tool_calls=[call("load_toolkit", '{"name": "kit"}')]), Reply(text="ok")],
                       flags={"movies": True})
    _, msgs, adapter = ask_in(ctx, [Reply(tool_calls=[call("kit_ping")]), Reply(text="x")], conv=cid,
                              flags={"movies": False})
    assert "kit_ping" not in names(adapter)
    assert [m["content"] for m in msgs if m["role"] == "tool"][-1] == "error: unknown tool: kit_ping"


def test_every_registered_tool_has_toolkit_and_risk():
    assert all(t.toolkit in manifests() and t.risk in ("safe", "risky") for t in REGISTRY.values())
    assert all(t.activity for t in REGISTRY.values())
    assert {t.name for t in REGISTRY.values() if t.risk == "risky"} >= {
        "propose_change", "remember", "finance_import_statement"
    }
