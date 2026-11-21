"""schedule_task: Ka saves a job the loop runs later (remember saves a fact instead)."""

from datetime import datetime

from pydantic import Field, field_validator

from server.agent.tools.registry import PendingWrite, ToolContext, ToolError, tool
from server.integrations.data_repo.schemas.common import KaModel


class ScheduleTaskArgs(KaModel):
    name: str = Field(min_length=1, max_length=80)
    brief: str = Field(min_length=5, max_length=2000)
    trigger: dict  # {"type": "interval", "minutes": N} or {"type": "cron", "hour": H, "minute": M, "day_of_week": "mon"}
    toolkits: list[str] = []

    @field_validator("trigger")
    @classmethod
    def _valid(cls, v: dict) -> dict:
        from server.loops.triggers import check_trigger

        try:
            check_trigger(v)
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"bad trigger: {e}") from e
        if v.get("type") == "interval" and int(v["minutes"]) < 15:
            raise ValueError("run at most every 15 minutes")
        return v


@tool(
    "schedule_task",
    "Save a task that runs on a schedule (e.g. check spending every Monday at 8). The owner "
    "approves it first; it starts in shadow mode, so its changes wait in Pending.",
    ScheduleTaskArgs,
    risk="risky",
    approval=True,
    flag="loops",
    activity="Proposed a scheduled task",
)
def schedule_task(args: ScheduleTaskArgs, ctx: ToolContext):
    from server.loops.tasks import ScheduledTask, TaskStore
    from server.toolkits.base import available

    if ctx.db is None:
        raise ToolError("conversation store not available")
    known = {m.name for m in available(ctx.config)}
    unknown = [k for k in args.toolkits if k not in known]
    if unknown:
        raise ToolError(f"unknown toolkits: {', '.join(unknown)}")
    task = ScheduledTask(
        name=args.name, kind="agent", trigger=args.trigger, brief=args.brief,
        toolkits=args.toolkits, created_by="ka",
    )  # fmt: skip
    db = ctx.db

    def apply() -> str:
        from server.loops import triggers

        tid = TaskStore(db).add(task, datetime.now())
        triggers.notify(db.user_id)
        return f"scheduled {tid} (shadow mode: its changes wait in Pending)"

    diff = f"name: {task.name}\ntrigger: {task.trigger}\ntoolkits: {task.toolkits}\nbrief: {task.brief}"
    return PendingWrite(summary=f"New scheduled task: {task.name}", diff=diff, apply=apply)
