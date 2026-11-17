"""Read tools over imported transactions."""

from datetime import date
from decimal import Decimal

from pydantic import Field, model_validator

from server.finance.queries import coverage, find_transactions, sum_rows, summarise
from server.finance.statements import list_statement_files
from server.integrations.data_repo.schemas.common import KaModel

from .registry import ToolContext, tool


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
)
def finance_summary(args: PeriodArgs, ctx: ToolContext):
    return summarise(ctx.store.transactions(), args.start, args.end)


@tool(
    "finance_coverage",
    "Which dates the imported finance data covers: overall range, rows per month and each "
    "statement's period. Call it when the period is unclear or a summary comes back empty. "
    "A statement can straddle two months, so a month may be only partly covered.",
    NoArgs,
)
def finance_coverage(args: NoArgs, ctx: ToolContext):
    return coverage(ctx.store.transactions(), ctx.store.statements())


@tool(
    "search_transactions",
    "Find transactions by text (case and spaces ignored), date range, tag, category or amount.",
    SearchArgs,
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


@tool("sum_transactions", "Exact signed total of transactions by row id.", SumArgs)
def sum_transactions(args: SumArgs, ctx: ToolContext):
    total, missing = sum_rows(ctx.store.transactions(), args.ids)
    return {"total": total, "count": len(args.ids) - len(missing), "missing": missing}


@tool("list_statements", "List statement PDFs and whether each is already imported.", NoArgs)
def list_statements(args: NoArgs, ctx: ToolContext):
    return {"files": list_statement_files(ctx.config, ctx.store)}
