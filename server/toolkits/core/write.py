"""Write tools. Approval-gated ones return a PendingWrite; nothing is written until apply()."""

from typing import Literal

from pydantic import Field

from server.agent.tools.registry import PendingWrite, ToolContext, ToolError, tool
from server.integrations.data_repo.schemas.common import KaModel
from server.integrations.data_repo.writer import ChangeError, Patch, apply_change, plan_change


class RememberArgs(KaModel):
    text: str = Field(min_length=1)
    type: Literal["fact", "preference", "rule"] = "fact"
    toolkit: str = Field(default="core", pattern=r"^[a-z]+$")  # which memory file


FINANCE_TARGETS = {"account", "merchant_rule", "transaction_type"}


@tool(
    "propose_change",
    "Propose an edit to personal data (profile, jobs, highlights, guardrails, accounts, ...). "
    "Shows a diff; nothing is saved until the owner approves. A job is addressed by the `key` get_jobs returns.",
    Patch,
    approval=True,
    risk="risky",
    activity="Proposed a change to your data",
)
def propose_change(args: Patch, ctx: ToolContext):
    root = ctx.config.data_repo
    if args.target in FINANCE_TARGETS:
        ctx.mark_private()  # the diff shows account or merchant data
    try:
        plan = plan_change(root, args)
    except ChangeError as e:
        raise ToolError(str(e)) from e

    def apply() -> str:
        try:
            return f"committed {apply_change(root, plan)}"
        except ChangeError as e:
            raise ToolError(str(e)) from e

    return PendingWrite(summary=plan.message, diff=plan.diff, apply=apply)


@tool(
    "remember",
    "Save something the owner explicitly asked you to remember. Saves immediately.",
    RememberArgs,
    risk="risky",
    activity="Saved a memory",
)
def remember(args: RememberArgs, ctx: ToolContext):
    today = ctx.today().isoformat()
    patch = Patch(
        target="memory",
        op="add",
        scope=args.toolkit,
        fields={
            "type": args.type,
            "text": args.text,
            "created": today,
            "updated": today,
            "status": "active",
        },
    )
    try:
        plan = plan_change(ctx.config.data_repo, patch)
        commit = apply_change(ctx.config.data_repo, plan)
    except ChangeError as e:
        raise ToolError(str(e)) from e
    return {"id": plan.key, "commit": commit}
