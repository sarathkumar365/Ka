"""What each model call sees beyond the stored history."""

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
