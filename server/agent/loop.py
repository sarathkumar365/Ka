"""The agent loop: model call, tools, approval, repeat. Knows only interfaces, never a provider."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from server.store.db import Db

from .adapters import Adapter, ToolCall, tool_specs
from .prompt import build_system_prompt
from .tools import REGISTRY, PendingWrite, ToolContext, ToolError, run_tool

MAX_TOOL_CALLS = 10


@dataclass
class Event:
    kind: Literal["tool_call", "tool_result", "approval", "answer", "stopped"]
    data: dict = field(default_factory=dict)


def _execute(
    call: ToolCall, ctx: ToolContext, approve: Callable[[PendingWrite], bool], emit, owner_text: str
) -> str:
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return "invalid JSON arguments"
    if not isinstance(args, dict):
        return "invalid JSON arguments: expected an object"
    if call.name == "remember" and "remember" not in owner_text.lower():
        # remember saves with no approval and lands in the system prompt, so only an explicit ask may use it
        return "error: the owner did not ask you to remember anything; use propose_memory instead"
    emit(Event("tool_call", {"name": call.name, "args": args}))
    try:
        result = run_tool(call.name, args, ctx)
        if isinstance(result, PendingWrite):
            emit(Event("approval", {"summary": result.summary, "diff": result.diff}))
            if not approve(result):
                return "user declined; nothing was changed"
            try:
                return result.apply()
            except ToolError as e:
                return f"failed: {e}"
        return json.dumps(result, default=str)
    except ToolError as e:
        return f"error: {e}"
    except Exception as e:  # noqa: BLE001  a broken tool must not kill the turn; the model sees the failure
        return f"error: {type(e).__name__}: {e}"


def run_turn(
    user_text: str,
    *,
    conv_id: str,
    db: Db,
    adapter: Adapter,
    ctx: ToolContext,
    approve: Callable[[PendingWrite], bool],
    on_event: Callable[[Event], None] = lambda e: None,
    now: Callable[[], datetime] = datetime.now,
    private_adapter: Adapter | None = None,
) -> str:
    ctx.db, ctx.conversation_id = db, conv_id
    if private_adapter is not None and db.is_private(conv_id):
        adapter = private_adapter
    system = {"role": "system", "content": build_system_prompt(ctx.data, ctx.today())}
    specs = tool_specs(REGISTRY)
    db.add_message(conv_id, {"role": "user", "content": user_text}, now())
    used = 0
    last = ""
    while True:
        reply = adapter.complete([system, *db.messages(conv_id)], specs)
        text = reply.text if reply.tool_calls else (reply.text or "(no answer)")
        message: dict = {"role": "assistant", "content": text}
        if reply.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in reply.tool_calls
            ]
        db.add_message(conv_id, message, now())
        if not reply.tool_calls:
            answer = text
            on_event(Event("answer", {"text": answer}))
            return answer
        refused = False
        for c in reply.tool_calls:
            if used >= MAX_TOOL_CALLS:
                refused, result = True, "step limit reached; no more tool calls this question"
            else:
                used += 1
                last = f"{c.name} {c.arguments}"
                result = _execute(c, ctx, approve, on_event, user_text)
                tool = REGISTRY.get(c.name)
                if private_adapter is not None and tool is not None and tool.private:
                    db.mark_private(conv_id)
                if private_adapter is not None and db.is_private(conv_id):
                    # finance data is now in the history: nothing more goes to the default model
                    adapter = private_adapter
                on_event(Event("tool_result", {"name": c.name, "result": result}))
            db.add_message(
                conv_id, {"role": "tool", "tool_call_id": c.id, "content": result}, now()
            )
        if refused:
            answer = (
                f"Stopped after {MAX_TOOL_CALLS} tool calls without an answer. Last step: {last}"
            )
            db.add_message(conv_id, {"role": "assistant", "content": answer}, now())
            on_event(Event("stopped", {"text": answer}))
            return answer
