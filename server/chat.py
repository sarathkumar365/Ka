"""Terminal chat: the owner's side of the loop (prompt, approvals, saving)."""

from collections.abc import Callable
from datetime import datetime

from server.agent.adapters import Adapter, AdapterError
from server.agent.loop import Event, run_turn
from server.agent.tools import PendingWrite, ToolContext
from server.config import Config
from server.finance.store import CsvFinanceStore
from server.store.db import Db


def terminal_approve(
    p: PendingWrite, ask: Callable[[str], str] = input, out: Callable[[str], None] = print
) -> bool:
    out(f"\nApproval needed: {p.summary}")
    if p.diff:
        out(p.diff)
    try:
        return ask("Apply this? [y/N] ").strip().lower() == "y"
    except EOFError:  # no terminal attached: treat as no
        return False


def chat_loop(
    cfg: Config,
    adapter: Adapter,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
    resume: str | None = None,
    private_adapter: Adapter | None = None,
) -> None:
    db = Db(cfg.db_path)
    if resume and not db.conversation_exists(resume):
        out(f"no such conversation: {resume}")
        return
    conv_id = resume or db.new_conversation(datetime.now())
    ctx = ToolContext(config=cfg, store=CsvFinanceStore(cfg.finance_dir), db=db)
    out(f"conversation {conv_id} (type 'exit' to leave; resume with --resume {conv_id})")

    def show(e: Event) -> None:
        if e.kind == "tool_call":
            out(f"  [tool] {e.data['name']} {e.data['args']}")

    while True:
        try:
            text = ask("you> ").strip()
        except EOFError:
            return
        if text in ("exit", "quit"):
            return
        if not text:
            continue
        try:
            answer = run_turn(
                text,
                conv_id=conv_id,
                db=db,
                adapter=adapter,
                ctx=ctx,
                approve=lambda p: terminal_approve(p, ask, out),
                on_event=show,
                private_adapter=private_adapter,
            )
        except AdapterError as e:
            out(f"error: {e}")
            continue
        out(answer)
