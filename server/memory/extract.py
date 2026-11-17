"""Nightly extraction: read a day's chats, queue new facts. The owner approves them later."""

import json
import logging
from datetime import date, datetime

from server.agent.adapters import Adapter, AdapterError
from server.integrations.data_repo.loader import KaData
from server.store.db import Db

from .pending import PendingError, queue_memory

log = logging.getLogger(__name__)

FINANCE_TOOLS = {
    "search_transactions",
    "sum_transactions",
    "finance_summary",
    "list_statements",
    "import_statement",
}
TRIM = 500
TYPES = {"fact", "preference", "rule"}

INSTRUCTION = """You read one conversation between the owner and their assistant and list NEW
lasting things worth remembering about the owner: facts, preferences, rules. Ignore one-off
requests, questions and anything about money amounts. Reply with only a JSON array of objects
{"type": "fact"|"preference"|"rule", "text": "...", "replaces": "M-xxxx" or null}. Use "replaces"
only when the new item contradicts one of the existing memories below. Empty array if nothing.

Existing memories:
"""


def _transcript(messages: list[dict]) -> str:
    names = {c["id"]: c["function"]["name"] for m in messages for c in (m.get("tool_calls") or [])}
    lines = []
    for m in messages:
        if m["role"] == "tool":
            if names.get(m["tool_call_id"]) in FINANCE_TOOLS:
                lines.append("tool: [finance result omitted]")
            else:
                lines.append(f"tool: {str(m['content'])[:TRIM]}")
        elif m.get("content"):
            lines.append(f"{m['role']}: {m['content']}")
    return "\n".join(lines)


def parse_items(text: str) -> list[dict]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("text"), str)]


def extract_memories(day: date, db: Db, data: KaData, adapter: Adapter, now: datetime) -> int:
    existing = (
        "\n".join(f"{e.id}: {e.text}" for e in data.memory.entries if e.status == "active")
        or "(none)"
    )
    queued = 0
    failed = 0
    done_key = f"extraction_done:{day.isoformat()}"
    # A retried day skips chats that already succeeded: a second pass rewords facts into duplicates.
    done = set(json.loads(db.get_state(done_key) or "[]"))
    for cid in db.conversations_on(day):
        if cid in done:
            continue
        messages = db.messages(cid)
        if not any(m["role"] == "user" for m in messages):
            continue
        prompt = [
            {"role": "system", "content": INSTRUCTION + existing},
            {"role": "user", "content": _transcript(messages)},
        ]
        try:
            reply = adapter.complete(prompt, [])
        except AdapterError as e:
            log.warning("extraction skipped for %s: %s", cid, e)
            failed += 1
            continue
        for item in parse_items(reply.text or ""):
            kind = item.get("type") if item.get("type") in TYPES else "fact"
            try:
                result = queue_memory(db, data, item["text"], kind, item.get("replaces"), cid, now)
            except PendingError as e:
                log.warning("dropped item from %s: %s", cid, e)
                continue
            queued += result["queued"]
        done.add(cid)
        db.set_state(done_key, json.dumps(sorted(done)))
    if failed:
        # Items already queued stay (the queue dedupes a retry); the day must be tried again.
        raise AdapterError(f"model unavailable for {failed} conversation(s) on {day}")
    return queued
