from server.agent.tools import run_tool
from server.store.db import Db


def test_propose_memory_queues_with_conversation_as_source(ctx):
    ctx.db, ctx.conversation_id = Db(":memory:"), "C-1"
    out = run_tool("propose_memory", {"text": "Owns a bike", "type": "fact"}, ctx)
    assert out["queued"] is True
    [item] = ctx.db.list_pending()
    assert item.source == "C-1" and item.payload["text"] == "Owns a bike"
    assert run_tool("propose_memory", {"text": "owns a bike"}, ctx)["reason"] == "duplicate"
