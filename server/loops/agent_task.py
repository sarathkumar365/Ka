"""Agent tasks: a saved brief run through the normal agent loop, headless and inside limits."""

from datetime import datetime

from server.agent.loop import Event, run_turn
from server.agent.tools import PendingWrite, ToolContext
from server.memory.pending import queue_tool_write

from .runner import BudgetAdapter, RunContext
from .tasks import ScheduledTask


def agent_task_body(
    task: ScheduledTask, rc: RunContext, ctx: ToolContext, adapter, now: datetime,
    private_adapter=None,
) -> dict:
    """private_adapter: the finance chain; once finance data is read, the rest goes there."""
    db = ctx.db
    conv = db.new_conversation(now)
    for name in task.toolkits:
        db.add_toolkit(conv, name, now)
    queued: list[int] = []
    direct = task.mode == "direct"

    def queue(tool: str, args: dict, proposal: PendingWrite | None, after_untrusted: bool) -> str:
        summary = proposal.summary if proposal else f"{tool}: {args.get('text') or args}"
        diff = proposal.diff if proposal else ""
        queued.append(
            queue_tool_write(
                db, tool, args, summary, diff, rc.run_id, now, after_untrusted, task_id=task.id
            )
        )
        return "queued for the owner's approval; nothing was changed yet"

    def on_event(e: Event) -> None:
        if e.kind == "tool_call":
            rc.budget.charge_tool()

    answer = run_turn(
        task.brief, conv_id=conv, db=db, adapter=BudgetAdapter(adapter, rc.budget), ctx=ctx,
        # shadow: every risky call becomes a card; direct: writes apply (still blocked after
        # untrusted content, like a chat)
        approve=lambda p: direct, on_event=on_event, now=lambda: now,
        queue_risky=None if direct else queue,
        private_adapter=BudgetAdapter(private_adapter, rc.budget) if private_adapter else None,
    )  # fmt: skip
    if queued:
        db.add_activity(
            "loop", f"{task.name} queued {len(queued)} change(s) for approval", now, conv
        )
    return {"answer": answer, "conversation_id": conv, "queued": len(queued)}
