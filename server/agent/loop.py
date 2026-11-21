"""The agent loop: model call, tools, approval, repeat. Knows only interfaces, never a provider."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from server.store.db import Db
from server.toolkits.base import available, visible_tools
from server.tracing import tool_span, turn_span

from .adapters import Adapter, ToolCall, tool_specs
from .context import compact_history
from .prompt import build_system_prompt
from .tools import REGISTRY, PendingWrite, ToolContext, ToolError, run_tool

MAX_TOOL_CALLS = 10
BLOCKED = "blocked: untrusted content was read this turn; ask the owner to confirm in a new message"


# remember skips approval, so only a message that starts by asking for it counts: "remember that
# ...", "please remember ...". "I don't remember that charge" does not.
ASKED_TO_REMEMBER = re.compile(
    r"\s*(?:(?:please|ka|hey ka)[\s,]+)?(?:(?:can|could|will) you\s+)?remember\b", re.IGNORECASE
)


def wrap_untrusted(tool_name: str, payload: str) -> str:
    """Mark outside text as data. The payload cannot close the tag early."""
    safe = payload.replace("</untrusted", "<\\/untrusted")
    return f'<untrusted source="{tool_name}">{safe}</untrusted>'


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
    if call.name == "remember" and not ASKED_TO_REMEMBER.match(owner_text):
        # remember saves with no approval and lands in the system prompt, so only an explicit ask may use it
        return "error: the owner did not ask you to remember anything; use propose_memory instead"
    emit(Event("tool_call", {"name": call.name, "args": args}))
    private = lambda: ctx.db is not None and ctx.db.is_private(ctx.conversation_id)
    with tool_span(call.name, args, private) as span:
        text = _run(call, args, ctx, approve, emit)
        span.result(text)
    return text


def _run(call: ToolCall, args: dict, ctx: ToolContext, approve, emit) -> str:
    try:
        result = run_tool(call.name, args, ctx)
        if isinstance(result, PendingWrite):
            emit(Event("approval", {"summary": result.summary, "diff": result.diff}))
            if not approve(result):
                return "user declined; nothing was changed"
            try:
                applied = result.apply()
            except ToolError as e:
                return f"failed: {e}"
            tool = REGISTRY.get(call.name)
            return wrap_untrusted(call.name, applied) if tool is not None and tool.untrusted else applied
        text = json.dumps(result, default=str)
        tool = REGISTRY.get(call.name)
        return wrap_untrusted(call.name, text) if tool is not None and tool.untrusted else text
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
    queue_risky: Callable[[str, dict, PendingWrite | None, bool], str] | None = None,
    hidden: frozenset[str] = frozenset(),
) -> str:
    """queue_risky set means headless (a loop): no one can answer, so every risky call becomes a
    card for the owner instead of running, remember included, and nothing is blocked."""
    with turn_span("chat turn", db.user_id, conv_id, user_text, lambda: db.is_private(conv_id)):
        return _turn(
            user_text, conv_id, db, adapter, ctx, approve, on_event, now, private_adapter,
            queue_risky, hidden,
        )  # fmt: skip


def _queue(c: ToolCall, ctx: ToolContext, queue_risky, tainted: bool) -> str:
    try:
        args = json.loads(c.arguments or "{}")
    except json.JSONDecodeError:
        return "invalid JSON arguments"
    if not isinstance(args, dict):
        return "invalid JSON arguments: expected an object"
    tool = REGISTRY[c.name]
    proposal = None
    if tool.approval:  # build the diff now; the owner sees it on the card
        try:
            proposal = run_tool(c.name, args, ctx)
        except ToolError as e:
            return f"error: {e}"
        except Exception as e:  # noqa: BLE001  a broken tool must not kill a loop run
            return f"error: {type(e).__name__}: {e}"
    return queue_risky(c.name, args, proposal, tainted)


def _turn(
    user_text, conv_id, db, adapter, ctx, approve, on_event, now, private_adapter, queue_risky,
    hidden=frozenset(),
) -> str:
    ctx.db, ctx.conversation_id = db, conv_id
    if private_adapter is not None and db.is_private(conv_id):
        adapter = private_adapter
    system = {
        "role": "system",
        "content": build_system_prompt(ctx.data, ctx.today(), available(ctx.config)),
    }
    start = len(db.messages(conv_id))  # this turn's user message lands at this index
    db.add_message(conv_id, {"role": "user", "content": user_text}, now())
    used = 0
    tainted = False  # per turn: the next owner message starts clean
    last = ""
    while True:
        visible = [  # load_toolkit adds more; a loop run hides some
            t for t in visible_tools(ctx.config, db.loaded_toolkits(conv_id)) if t.name not in hidden
        ]
        names = {t.name for t in visible}
        reply = adapter.complete(
            [system, *compact_history(db.messages(conv_id), start)], tool_specs(visible)
        )
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
        # A risky call is blocked once outside text was read this turn, or when another call in
        # the same reply reads some (the model may have planned both before seeing it). A call
        # never taints itself, so an untrusted risky tool like a statement import still runs.
        readers = {c.id for c in reply.tool_calls if c.name in names and REGISTRY[c.name].untrusted}
        for c in reply.tool_calls:
            if used >= MAX_TOOL_CALLS:
                refused, result = True, "step limit reached; no more tool calls this question"
            else:
                used += 1
                last = f"{c.name} {c.arguments}"
                tool = REGISTRY.get(c.name)
                risky = tool is not None and tool.risk == "risky"
                if c.name in names and risky and queue_risky is not None:
                    on_event(Event("tool_call", {"name": c.name, "args": {}}))
                    result = _queue(c, ctx, queue_risky, bool(tainted or readers - {c.id}))
                elif c.name in names and risky and (tainted or readers - {c.id}):
                    result = BLOCKED
                    db.add_activity(
                        "blocked", f"Blocked {c.name} after untrusted content", now(), conv_id
                    )
                elif c.name in names:
                    result = _execute(c, ctx, approve, on_event, user_text)
                    tainted = tainted or (tool is not None and tool.untrusted)
                else:  # not loaded, flagged off or made up: the model must not reach it
                    result = f"error: unknown tool: {c.name}"
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
