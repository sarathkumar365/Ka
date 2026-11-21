"""What each model call sees beyond the stored history, and what earlier turns let a tool do."""

import re

WEB_TOOLS = {"web_search", "fetch_page"}
REMOVED = "[web results from an earlier turn removed]"


def compact_history(messages: list[dict], current_turn_start: int) -> list[dict]:
    """Drop web results from earlier turns: they were used then and cost tokens every step now.

    Only the model input changes; the stored conversation keeps everything.
    """
    web_calls = {
        c["id"]
        for m in messages[:current_turn_start]
        if m.get("role") == "assistant"
        for c in m.get("tool_calls") or []
        if c["function"]["name"] in WEB_TOOLS
    }
    out = []
    for i, m in enumerate(messages):
        if i < current_turn_start and m.get("role") == "tool" and m.get("tool_call_id") in web_calls:
            m = {**m, "content": REMOVED}
        out.append(m)
    return out


URL = re.compile(r"https?://[^\s\"'<>()\[\]{}]+")


def norm_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/.,;:!?")


def _tool_names(messages: list[dict]) -> dict[str, str]:
    return {
        c["id"]: c["function"]["name"]
        for m in messages
        if m.get("role") == "assistant"
        for c in m.get("tool_calls") or []
    }


def conversation_read_untrusted(messages: list[dict]) -> bool:
    """A tool in this conversation already returned outside text (web, statements, movies).

    Only calls with a stored result count: the call being run right now is in the history too."""
    from server.agent.tools.registry import REGISTRY

    names = _tool_names(messages)
    from server.store.db import INTERRUPTED

    done = {
        m.get("tool_call_id")
        for m in messages
        if m.get("role") == "tool" and m.get("content") != INTERRUPTED
    }
    return any(
        names[i] in REGISTRY and REGISTRY[names[i]].untrusted for i in done if i in names
    )


def known_urls(messages: list[dict]) -> set[str]:
    """Links the person typed, or that a web search returned: safe to open after outside text."""
    names = _tool_names(messages)
    found: set[str] = set()
    for m in messages:
        from_search = m.get("role") == "tool" and names.get(m.get("tool_call_id")) == "web_search"
        if m.get("role") == "user" or from_search:
            found |= {norm_url(u) for u in URL.findall(m.get("content") or "")}
    return found
