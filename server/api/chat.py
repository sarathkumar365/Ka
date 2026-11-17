"""POST /api/chat streams one turn as SSE; POST /api/approvals/{id} answers a write approval."""

import json
import logging
import queue
import threading
from datetime import datetime

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.agent.adapters import AdapterError
from server.agent.loop import Event, run_turn
from server.agent.tools import PendingWrite, ToolContext
from server.finance.store import CsvFinanceStore
from server.store.db import Db

from .describe import describe_call

router = APIRouter()
log = logging.getLogger(__name__)
GENERIC_ERROR = "Something went wrong."


class ChatBody(BaseModel):
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=8000)


class ApprovalBody(BaseModel):
    approve: bool


def frame(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def _outcome(result: str) -> str:
    if result.startswith("user declined"):
        return " You declined it."
    if result.startswith(("failed", "error")):
        return " It did not go through."
    return " You approved it."


@router.post("/chat")
def chat(body: ChatBody, request: Request):
    state = request.app.state
    cfg = state.cfg
    probe = Db(cfg.db_path)
    try:
        if body.conversation_id and not probe.conversation_exists(body.conversation_id):
            raise HTTPException(404, "no such conversation")
        with state.lock:
            if body.conversation_id in state.running:
                raise HTTPException(409, "a turn is already running in this conversation")
            conv_id = body.conversation_id or probe.new_conversation(datetime.now())
            state.running.add(conv_id)
    finally:
        probe.conn.close()

    out: queue.Queue = queue.Queue()
    cancelled = threading.Event()
    open_ids: list[str] = []

    def approve(p: PendingWrite) -> bool:
        if cancelled.is_set():
            return False
        approval_id = state.broker.request()
        open_ids.append(approval_id)
        if cancelled.is_set():  # the stream closed between the check above and now
            state.broker.resolve(approval_id, False)
        out.put(("approval", {"approval_id": approval_id, "summary": p.summary, "diff": p.diff}))
        return state.broker.wait(approval_id, state.approval_timeout) and not cancelled.is_set()

    def work() -> None:
        db: Db | None = None
        last_args: dict = {}
        out.put(("conversation", {"id": conv_id}))

        def on_event(e: Event) -> None:
            nonlocal last_args
            if e.kind == "tool_call":
                last_args = e.data["args"]
                out.put(("tool_call", e.data))
            elif e.kind == "tool_result":
                out.put(("tool_result", e.data))
                kind, text = describe_call(e.data["name"], last_args, e.data["result"])
                if kind == "change":
                    text += _outcome(e.data["result"])
                assert db is not None
                db.add_activity(kind, text, datetime.now(), conv_id)
            elif e.kind in ("answer", "stopped"):
                out.put((e.kind, e.data))

        try:
            db = Db(cfg.db_path)
            adapter = state.adapter_factory()
            ctx = ToolContext(config=cfg, store=CsvFinanceStore(cfg.finance_dir), db=db)
            run_turn(
                body.text,
                conv_id=conv_id,
                db=db,
                adapter=adapter,
                ctx=ctx,
                approve=approve,
                on_event=on_event,
            )
        except AdapterError as e:
            if db:
                db.add_activity(
                    "error", f"The model could not answer: {e}", datetime.now(), conv_id
                )
            out.put(("error", {"message": str(e)}))
        except Exception:  # never leak internals to the browser
            log.exception("chat turn failed")
            out.put(("error", {"message": GENERIC_ERROR}))
        finally:
            state.running.discard(conv_id)
            if db:
                db.conn.close()
            out.put(("done", {}))
            out.put(None)

    threading.Thread(target=work, daemon=True).start()

    async def stream():
        try:
            while True:
                try:  # short polls so a closed connection cancels us within a second
                    item = await anyio.to_thread.run_sync(lambda: out.get(timeout=1))
                except queue.Empty:
                    continue
                if item is None:
                    break
                yield frame(*item)
        finally:  # client gone: stop waiting on any open approval
            cancelled.set()
            state.broker.cancel_all(list(open_ids))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/approvals/{approval_id}")
def answer_approval(approval_id: str, body: ApprovalBody, request: Request):
    if not request.app.state.broker.resolve(approval_id, body.approve):
        raise HTTPException(404, "no such open approval")
    return {"ok": True}
