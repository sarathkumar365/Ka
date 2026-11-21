"""Core web tools: search returns a few short highlights with links; fetch_page reads one page."""

import json
import re

from pydantic import Field

from server.agent.context import conversation_read_untrusted, known_urls, norm_url
from server.agent.tools.registry import PendingWrite, ToolContext, ToolError, to_json, tool
from server.integrations.data_repo.schemas.common import KaModel
from server.web.providers import MAX_RESULTS, fetch_page, web_search


class WebSearchArgs(KaModel):
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=MAX_RESULTS, ge=1, le=MAX_RESULTS)


class FetchPageArgs(KaModel):
    url: str = Field(min_length=8, max_length=2000)


def _personal_terms(ctx: ToolContext) -> list[str]:
    accounts = ctx.data.accounts.accounts
    return [t.lower() for a in accounts for t in (a.label, a.bank) if t and len(t) >= 3]


def _refuse_personal(query: str, ctx: ToolContext) -> None:
    """In a finance chat nothing personal may leave in a query: it goes to an outside company."""
    if ctx.db is None or ctx.conversation_id is None or not ctx.db.is_private(ctx.conversation_id):
        return
    low = query.lower()
    if re.search(r"\d{4,}", query) or any(t in low for t in _personal_terms(ctx)):
        raise ToolError("query looks personal; rephrase it without amounts or account names")


def _summariser(ctx: ToolContext):
    """Small model for long pages; in a private chat the private chain, or plain cutting."""
    from server.agent.adapters import AdapterError, build_adapter

    try:
        private = (
            ctx.db is not None and ctx.conversation_id and ctx.db.is_private(ctx.conversation_id)
        )
        if private:
            if not ctx.config.private_models:
                return None
            from server.agent.adapters.chain import build_private_adapter

            adapter = build_private_adapter(ctx.config)
        else:
            model = ctx.config.models.get("small") or ctx.config.models.get("default")
            if model is None:
                return None
            adapter = build_adapter(model)
    except AdapterError:
        return None

    if ctx.wrap_adapter is not None:
        adapter = ctx.wrap_adapter(adapter)

    def summarise(text: str) -> str:
        msg = "Summarise this web page in at most 300 words. Keep facts, numbers and dates.\n\n"
        return adapter.complete([{"role": "user", "content": msg + text}], []).text or ""

    return summarise


@tool(
    "web_search",
    "Search the web. Returns up to 5 short highlights, each with title, link and date. Use for "
    "recent or fast-changing facts; never for the owner's own data. Read a full page with "
    "fetch_page.",
    WebSearchArgs,
    untrusted=True,
    flag="web_search",
    activity="Searched the web",
)
def search(args: WebSearchArgs, ctx: ToolContext):
    _refuse_personal(args.query, ctx)
    return {"results": web_search(args.query, args.limit)}


@tool(
    "fetch_page",
    "Read one public web page as text (menus and footers removed; long pages are shortened).",
    FetchPageArgs,
    untrusted=True,
    flag="web_search",
    activity="Read a web page",
)
def page(args: FetchPageArgs, ctx: ToolContext):
    _refuse_personal(args.url, ctx)  # a URL can carry data out as easily as a query
    # After outside text, a link the person never saw could be text telling Ka to send data out
    # in a query string. Links from the person or from search results open; anything else asks.
    history = ctx.db.messages(ctx.conversation_id) if ctx.db and ctx.conversation_id else []
    if conversation_read_untrusted(history) and norm_url(args.url) not in known_urls(history):
        return PendingWrite(
            summary=f"Open {args.url}?",
            diff=args.url,
            apply=lambda: json.dumps(to_json(fetch_page(args.url, summarise=_summariser(ctx)))),
            outbound=True,
        )
    return fetch_page(args.url, summarise=_summariser(ctx))
