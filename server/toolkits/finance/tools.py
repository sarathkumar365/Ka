"""Read tools over imported transactions."""

from datetime import date
from decimal import Decimal

from pydantic import Field, model_validator

from server.agent.tools.registry import PendingWrite, ToolContext, ToolError, tool
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.parser import StatementFormatError
from server.finance.queries import coverage, find_transactions, sum_rows, summarise
from server.finance.statements import list_statement_files
from server.integrations.data_repo.schemas.common import KaModel


class PeriodArgs(KaModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self):
        if self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class SearchArgs(KaModel):
    query: str = ""
    start: date | None = None
    end: date | None = None
    tag: str | None = None
    category: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    limit: int = Field(default=50, ge=1, le=500)


class SumArgs(KaModel):
    ids: list[str] = Field(min_length=1)


class NoArgs(KaModel):
    pass


@tool(
    "finance_summary",
    "Spending, income and debt payments for an inclusive date range. "
    "Own-account transfers are never counted as spending.",
    PeriodArgs,
    toolkit="finance",
    private=True,
    activity="Summarised your spending",
)
def finance_summary(args: PeriodArgs, ctx: ToolContext):
    return summarise(ctx.store.transactions(), args.start, args.end)


@tool(
    "finance_coverage",
    "Which dates the imported finance data covers: overall range, rows per month and each "
    "statement's period. Call it when the period is unclear or a summary comes back empty. "
    "A statement can straddle two months, so a month may be only partly covered.",
    NoArgs,
    toolkit="finance",
    private=True,
    activity="Checked which months have data",
)
def finance_coverage(args: NoArgs, ctx: ToolContext):
    return coverage(ctx.store.transactions(), ctx.store.statements())


@tool(
    "finance_search_transactions",
    "Find transactions by text (case and spaces ignored), date range, tag, category or amount.",
    SearchArgs,
    untrusted=True,  # descriptions come from bank statements
    toolkit="finance",
    private=True,
    activity="Searched transactions",
)
def search_transactions(args: SearchArgs, ctx: ToolContext):
    found = find_transactions(
        ctx.store.transactions(),
        args.query,
        args.start,
        args.end,
        args.tag,
        args.category,
        args.min_amount,
        args.max_amount,
    )
    return {
        "rows": found[: args.limit],
        "total_matches": len(found),
        "truncated": len(found) > args.limit,
    }


@tool(
    "finance_sum_transactions",
    "Exact signed total of transactions by row id.",
    SumArgs,
    toolkit="finance",
    private=True,
    activity="Added up transactions",
)
def sum_transactions(args: SumArgs, ctx: ToolContext):
    total, missing = sum_rows(ctx.store.transactions(), args.ids)
    return {"total": total, "count": len(args.ids) - len(missing), "missing": missing}


@tool(
    "finance_list_statements",
    "List statement PDFs and whether each is already imported.",
    NoArgs,
    toolkit="finance",
    private=True,
    activity="Listed statements",
)
def list_statements(args: NoArgs, ctx: ToolContext):
    return {"files": list_statement_files(ctx.config, ctx.store)}


PREVIEW_ROWS = 10


class ImportArgs(KaModel):
    file_name: str


@tool(
    "finance_import_statement",
    "Import a Scotiabank statement PDF from the statements folder. Shows row count and totals; "
    "rows are written only after the owner approves.",
    ImportArgs,
    approval=True,
    risk="risky",
    untrusted=True,
    toolkit="finance",
    private=True,
    activity="Proposed a statement import",
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
