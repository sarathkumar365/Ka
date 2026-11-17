"""Write tools. Approval-gated ones return a PendingWrite; nothing is written until apply()."""

from typing import Literal

from pydantic import Field

from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.integrations.data_repo.schemas.common import KaModel
from server.integrations.data_repo.writer import ChangeError, Patch, apply_change, plan_change

from .registry import PendingWrite, ToolContext, ToolError, tool

PREVIEW_ROWS = 10


class RememberArgs(KaModel):
    text: str = Field(min_length=1)
    type: Literal["fact", "preference", "rule"] = "fact"


class ImportArgs(KaModel):
    file_name: str


@tool(
    "propose_change",
    "Propose an edit to personal data (profile, jobs, highlights, guardrails, accounts, ...). "
    "Shows a diff; nothing is saved until the owner approves.",
    Patch,
    mode="WRITE",
    approval=True,
)
def propose_change(args: Patch, ctx: ToolContext):
    root = ctx.config.data_repo
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
    mode="WRITE",
)
def remember(args: RememberArgs, ctx: ToolContext):
    today = ctx.today().isoformat()
    patch = Patch(
        target="memory",
        op="add",
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


@tool(
    "import_statement",
    "Import a Scotiabank statement PDF from the statements folder. Shows row count and totals; "
    "rows are written only after the owner approves.",
    ImportArgs,
    mode="WRITE",
    approval=True,
)
def import_statement(args: ImportArgs, ctx: ToolContext):
    name = args.file_name
    if "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".pdf"):
        raise ToolError("file_name must be a plain .pdf name from the statements folder")
    pdf = ctx.config.statements_dir / name
    if not pdf.is_file():
        raise ToolError(f"not found in statements folder: {name}")
    try:
        preview = prepare_import(pdf, ctx.data, ctx.store)
    except (ImportFailed, StatementFormatError) as e:
        raise ToolError(str(e)) from e
    if preview.failures:
        lines = "; ".join(f"{f.check} row {f.row_number}: {f.message}" for f in preview.failures)
        raise ToolError(f"checks failed, nothing to import: {lines}")
    if preview.already_imported:
        raise ToolError(f"already imported: {preview.statement.statement_id}")
    s = preview.statement
    summary = f"{len(preview.transactions)} rows, withdrawals {s.total_withdrawals}, deposits {s.total_deposits}, checks passed"
    if preview.unknown_types:
        summary += f"; unknown types: {', '.join(preview.unknown_types)}"
    if preview.unknown_merchants:
        summary += f"; {len(preview.unknown_merchants)} uncategorised merchants"
    diff = "\n".join(
        f"{t.date} {t.amount:>10} {t.tag:<12} {t.description}"
        for t in preview.transactions[:PREVIEW_ROWS]
    )
    return PendingWrite(
        summary=summary,
        diff=diff,
        apply=lambda: f"written {commit_import(preview, ctx.store)} rows",
    )
