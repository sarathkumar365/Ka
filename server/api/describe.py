"""One-sentence descriptions of tool calls for the activity log. Never echoes argument values."""

import json

from server.agent.tools import REGISTRY


def describe_call(name: str, args: dict, result: str) -> tuple[str, str]:
    tool = REGISTRY.get(name)
    kind = "change" if tool is not None and tool.risk == "risky" else "read"
    sentence = (tool.activity if tool is not None else "") or f"Used {name}"
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):  # results like {"rows": [...]}: count the list inside
        parsed = next(
            (parsed[k] for k in ("rows", "hits", "files") if isinstance(parsed.get(k), list)), None
        )
    if isinstance(parsed, list):
        sentence += f", {len(parsed)} row{'s' if len(parsed) != 1 else ''}"
    return kind, sentence + "."
