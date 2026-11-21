from datetime import UTC, datetime

from server.agent.tools import run_tool
from server.store.db import Db

NOW = datetime(2031, 4, 5, tzinfo=UTC)


def test_search_conversations_tool_returns_hits_as_json(ctx):
    ctx.db = Db(":memory:", "avery")
    cid = ctx.db.new_conversation(NOW)
    ctx.db.add_message(cid, {"role": "user", "content": "plan the Lisbon trip"}, NOW)
    out = run_tool("search_conversations", {"query": "lisbon"}, ctx)
    assert out["hits"][0]["conversation_id"] == cid
    assert "Lisbon" in out["hits"][0]["snippet"]
