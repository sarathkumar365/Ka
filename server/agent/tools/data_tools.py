"""Read tools over the YAML data files."""

from typing import Any

from pydantic import Field

from server.integrations.data_repo.loader import KaData
from server.integrations.data_repo.schemas.common import KaModel

from .registry import ToolContext, ToolError, tool

SNIPPET_CHARS = 160


class NoArgs(KaModel):
    pass


class JobsArgs(KaModel):
    include_retired: bool = False


class SearchArgs(KaModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


@tool("get_profile", "Return the owner's profile.", NoArgs)
def get_profile(args: NoArgs, ctx: ToolContext):
    return ctx.data.profile


@tool(
    "get_jobs",
    "Return work history: domains, jobs and their highlights (retired ones only on request). "
    "Each job has a `key` to use with propose_change.",
    JobsArgs,
)
def get_jobs(args: JobsArgs, ctx: ToolContext):
    out = ctx.data.jobs.model_dump(mode="json")
    if not args.include_retired:
        for job in out["jobs"]:
            job["highlights"] = [h for h in job["highlights"] if not h["retired"]]
    for job in out["jobs"]:
        job["key"] = (
            f"{job['company']}|{job['start']}"  # what propose_change needs to address a job
        )
    return out


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return "" if value is None else str(value)


def _records(data: KaData) -> list[tuple[str, str, str]]:
    def dump(m):
        return m.model_dump(mode="json")

    out = [("profile.yaml", "profile", _text(dump(data.profile)))]
    out += [("education.yaml", e.id, _text(dump(e))) for e in data.education.entries]
    out += [("jobs.yaml", d.id, _text(dump(d))) for d in data.jobs.domains]
    for job in data.jobs.jobs:
        out.append(
            (
                "jobs.yaml",
                f"{job.company}|{job.start}",
                _text(dump(job.model_copy(update={"highlights": []}))),
            )
        )
        out += [("jobs.yaml", h.id, _text(dump(h))) for h in job.highlights]
    out += [("guardrails.yaml", g.id, _text(dump(g))) for g in data.guardrails.rules]
    out += [("memory.yaml", m.id, _text(dump(m))) for m in data.memory.entries]
    out += [("accounts.yaml", a.id, _text(dump(a))) for a in data.accounts.accounts]
    out += [("rules/merchants.yaml", r.id, _text(dump(r))) for r in data.merchant_rules.rules]
    out += [("other.yaml", r.id, _text(dump(r))) for r in data.other.records]
    return out


@tool("search", "Keyword search across all personal data files.", SearchArgs)
def search(args: SearchArgs, ctx: ToolContext):
    needle = args.query.casefold().strip()
    if not needle:
        raise ToolError("query must not be blank")
    hits = [
        {"file": f, "id": i, "snippet": t[:SNIPPET_CHARS]}
        for f, i, t in _records(ctx.data)
        if needle in t.casefold()
    ]
    return {"hits": hits[: args.limit], "truncated": len(hits) > args.limit}
