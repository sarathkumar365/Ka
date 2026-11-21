import json
from datetime import datetime

from server.agent.adapters import FakeAdapter, Reply, ToolCall
from server.agent.tools import ToolContext
from server.finance.store import CsvFinanceStore
from server.loops.agent_task import agent_task_body
from server.loops.runner import run_task
from server.loops.tasks import ScheduledTask, TaskStore
from server.memory.pending import approve_tool_write
from server.store.db import Db
from tests.conftest import git

NOW = datetime(2031, 4, 5, 12, 0)
PATCH = json.dumps({"target": "account", "op": "update", "key": "A-01", "fields": {"label": "Zed"}})


def commits(cfg):
    return int(git(cfg.data_repo, "rev-list", "--count", "HEAD"))


def run_agent(ctx, replies, brief="fix the label"):
    db = Db(ctx.config.db_path, ctx.config.user_id)
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60},
                              brief=brief, created_by="ka"), NOW)
    ctx.db = db

    def body(t, rc):
        return agent_task_body(t, rc, ctx, FakeAdapter(replies), NOW)

    run_id = run_task(s.get(tid), db, body, NOW)
    return db, next(r for r in s.runs(tid) if r.id == run_id)


def test_agent_task_queues_writes_instead_of_applying(ctx):
    before = commits(ctx.config)
    db, run = run_agent(ctx, [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="queued")])
    assert run.status == "ok" and run.result["queued"] == 1 and run.tool_calls == 1
    assert commits(ctx.config) == before
    card = db.list_pending()[0]
    assert card.kind == "tool_write" and card.payload["tool"] == "propose_change" and "Zed" in card.payload["diff"]


def test_remember_in_a_loop_is_queued_too(ctx):
    before = commits(ctx.config)
    db, _ = run_agent(ctx, [Reply(tool_calls=[ToolCall("1", "remember", json.dumps({"text": "x"}))]), Reply(text="ok")],
                        brief="remember x")
    assert commits(ctx.config) == before and db.list_pending()[0].kind == "tool_write"


def test_approving_tool_write_applies_it(ctx):
    db, _ = run_agent(ctx, [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="q")])
    before = commits(ctx.config)
    tctx = ToolContext(config=ctx.config, store=CsvFinanceStore(ctx.config.finance_dir), db=db)
    out = approve_tool_write(db.list_pending()[0].id, tctx)
    assert commits(ctx.config) == before + 1 and out
    assert db.list_pending() == []


def test_schedule_task_needs_approval(ctx):
    from server.agent.loop import run_turn

    cfg = ctx.config.model_copy(update={"flags": {"loops": True}})
    ctx.config = cfg
    ctx.db = Db(cfg.db_path, cfg.user_id)
    cid = ctx.db.new_conversation(NOW)
    args = json.dumps({"name": "Spending check", "brief": "check my spending",
                       "trigger": {"type": "cron", "hour": 8, "minute": 0, "day_of_week": "mon"}})
    asked = []
    run_turn("every monday check my spending", conv_id=cid, db=ctx.db,
             adapter=FakeAdapter([Reply(tool_calls=[ToolCall("1", "schedule_task", args)]), Reply(text="ok")]),
             ctx=ctx, approve=lambda p: asked.append(p) or True)
    assert len(asked) == 1
    t = TaskStore(ctx.db).all()[0]
    assert t.created_by == "ka" and t.mode == "shadow" and t.name == "Spending check"


def test_finance_loop_uses_the_private_model(ctx):
    db = Db(ctx.config.db_path, ctx.config.user_id)
    s = TaskStore(db)
    tid = s.add(ScheduledTask(name="t", kind="agent", trigger={"type": "interval", "minutes": 60},
                              brief="sum my spending", toolkits=["finance"], created_by="ka"), NOW)
    ctx.db = db
    default = FakeAdapter([Reply(tool_calls=[ToolCall("1", "finance_coverage", "{}")])])
    private = FakeAdapter([Reply(text="private answer")])

    def body(t, rc):
        return agent_task_body(t, rc, ctx, default, NOW, private_adapter=private)

    run_task(s.get(tid), db, body, NOW)
    assert len(private.calls) == 1 and len(default.calls) == 1
