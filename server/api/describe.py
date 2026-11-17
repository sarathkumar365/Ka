"""One-sentence descriptions of tool calls for the activity log. Never echoes argument values."""

import json

READS = {
    "finance_summary": "Summarised your spending",
    "search_transactions": "Searched transactions",
    "sum_transactions": "Added up transactions",
    "list_statements": "Listed statements",
    "search_conversations": "Searched past chats",
    "get_jobs": "Read your jobs",
    "get_profile": "Read your profile",
}
WRITES = {
    "propose_change": "Proposed a change to your data",
    "remember": "Saved a memory",
    "propose_memory": "Suggested a memory",
    "import_statement": "Proposed a statement import",
}


def describe_call(name: str, args: dict, result: str) -> tuple[str, str]:
    kind = "change" if name in WRITES else "read"
    sentence = WRITES.get(name) or READS.get(name) or f"Used {name}"
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, list):
        sentence += f", {len(parsed)} row{'s' if len(parsed) != 1 else ''}"
    return kind, sentence + "."
