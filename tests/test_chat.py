from server.agent.adapters import FakeAdapter, Reply
from server.agent.tools import PendingWrite
from server.chat import chat_loop, terminal_approve
from server.config import Config
from server.store.db import Db


def pending():
    return PendingWrite(summary="data: update account A-01", diff="-a\n+b", apply=lambda: "ok")


def test_terminal_approve_only_yes_approves():
    out = []
    assert terminal_approve(pending(), ask=lambda q: "y", out=out.append) is True
    assert any("A-01" in line for line in out) and any("+b" in line for line in out)
    assert terminal_approve(pending(), ask=lambda q: "yes please", out=out.append) is False
    assert terminal_approve(pending(), ask=lambda q: "", out=out.append) is False

    def eof(q):
        raise EOFError

    assert terminal_approve(pending(), ask=eof, out=out.append) is False


def test_chat_loop_runs_two_turns_with_fake_adapter_and_saves_them(ctx):
    cfg: Config = ctx.config
    adapter = FakeAdapter([Reply(text="first answer"), Reply(text="second answer")])
    typed = iter(["hello", "again", "exit"])
    out = []
    chat_loop(cfg, adapter, ask=lambda q: next(typed), out=out.append)
    assert "first answer" in out and "second answer" in out
    db = Db(cfg.db_path)
    [cid] = [r[0] for r in db.conn.execute("select id from conversations")]
    texts = [m["content"] for m in db.messages(cid)]
    assert texts == ["hello", "first answer", "again", "second answer"]
    assert any(cid in line for line in out)  # tells the owner the id for --resume
