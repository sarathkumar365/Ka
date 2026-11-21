import json
from datetime import datetime

import pytest

from server.agent.adapters import FakeAdapter, Reply, ToolCall
from server.agent.loop import _queue, run_turn
from server.store.db import Db
from server.web.providers import Page, SearchResult

NOW = lambda: datetime(2031, 4, 5, 12, 0)
EVIL = "https://evil.example/?p=x"
FOUND = "https://news.example/story"


@pytest.fixture
def web(ctx, monkeypatch):
    import server.toolkits.core.web as w

    ctx.config = ctx.config.model_copy(update={"flags": {"web_search": True}})
    ctx.db = Db(":memory:", "avery")
    monkeypatch.setattr(w, "web_search", lambda q, n: [SearchResult(title="t", url=FOUND, snippet="s", published=None, source="t")])
    monkeypatch.setattr(w, "fetch_page", lambda url, summarise=None: Page(url=url, title="p", text="body", published=None, truncated=False))
    return ctx


def turn(ctx, cid, text, replies, approve):
    run_turn(text, conv_id=cid, db=ctx.db, adapter=FakeAdapter(replies), ctx=ctx, approve=approve, now=NOW)
    return [m["content"] for m in ctx.db.messages(cid) if m["role"] == "tool"]


def search_then_fetch(ctx, url, text="read it"):
    asked = []
    cid = ctx.db.new_conversation(NOW())
    turn(ctx, cid, "news?", [Reply(tool_calls=[ToolCall("s", "web_search", json.dumps({"query": "news"}))]), Reply(text="ok")], lambda p: True)
    tools = turn(ctx, cid, text, [Reply(tool_calls=[ToolCall("f", "fetch_page", json.dumps({"url": url}))]), Reply(text="done")],
                 lambda p: asked.append(p) or False)
    return tools, asked


def test_unknown_url_after_web_read_needs_approval(web):
    tools, asked = search_then_fetch(web, EVIL)
    assert len(asked) == 1 and tools[-1] == "user declined; nothing was changed"


def test_url_from_results_or_owner_opens_without_prompt(web):
    tools, asked = search_then_fetch(web, FOUND)
    assert asked == [] and "body" in tools[-1]
    tools, asked = search_then_fetch(web, "https://mine.example/page", text="open https://mine.example/page please")
    assert asked == [] and "body" in tools[-1]


def test_fresh_chat_fetch_has_no_prompt(web):
    asked = []
    cid = web.db.new_conversation(NOW())
    tools = turn(web, cid, "read", [Reply(tool_calls=[ToolCall("f", "fetch_page", json.dumps({"url": EVIL}))]), Reply(text="x")],
                 lambda p: asked.append(p) or False)
    assert asked == [] and "body" in tools[-1]


def test_remember_needs_a_clear_request(ctx):
    ctx.db = Db(":memory:", "avery")
    cid = ctx.db.new_conversation(NOW())
    call = [Reply(tool_calls=[ToolCall("r", "remember", json.dumps({"text": "moved to Leeds"}))]), Reply(text="x")]
    assert "did not ask" in turn(ctx, cid, "I don't remember that charge", call, lambda p: True)[-1]
    call = [Reply(tool_calls=[ToolCall("r2", "remember", json.dumps({"text": "moved to Leeds"}))]), Reply(text="x")]
    assert "did not ask" not in turn(ctx, cid, "Remember that I moved to Leeds", call, lambda p: True)[-1]


def test_malformed_queued_call_returns_error(ctx):
    assert _queue(ToolCall("q", "remember", "[1]"), ctx, lambda *a: "queued", False) == "invalid JSON arguments: expected an object"
