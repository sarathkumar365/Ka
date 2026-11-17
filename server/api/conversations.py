import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from server.store.db import Db

from .deps import get_db

router = APIRouter()


@router.get("/conversations")
def list_conversations(db: Db = Depends(get_db)):
    return [asdict(r) for r in db.list_conversations()]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, db: Db = Depends(get_db)):
    if not db.conversation_exists(conv_id):
        raise HTTPException(404, "no such conversation")
    return {"id": conv_id, "items": to_items(db.messages(conv_id))}


def to_items(messages: list[dict]) -> list[dict]:
    """Stored OpenAI-format messages -> UI items; a tool call and its result become one item."""
    results = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    items: list[dict] = []
    for m in messages:
        if m["role"] == "user" and m.get("content"):
            items.append({"kind": "user", "text": m["content"]})
        elif m["role"] == "assistant":
            for c in m.get("tool_calls") or []:
                fn = c["function"]
                try:
                    args = json.loads(fn["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                items.append(
                    {
                        "kind": "tool",
                        "name": fn["name"],
                        "args": args,
                        "result": results.get(c["id"]),
                    }
                )
            if m.get("content"):
                items.append({"kind": "assistant", "text": m["content"]})
    return items
