"""SQLite for conversations, messages (with full-text index) and the pending queue.

Every row carries user_id; a Db instance only sees and writes its own user's rows."""

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from .migrations import migrate


@dataclass
class SearchHit:
    conversation_id: str
    message_id: int
    role: str
    snippet: str
    at: str


@dataclass
class PendingItem:
    id: int
    kind: str
    payload: dict
    source: str | None
    status: str
    created_at: str


@dataclass
class ConversationRow:
    id: str
    title: str
    started_at: str
    last_at: str


@dataclass
class ActivityRow:
    id: int
    at: str
    kind: str
    text: str
    conversation_id: str | None


@dataclass
class IntakeJob:
    id: str
    kind: str
    status: str
    step: str
    message: str
    result: dict
    created_at: str


class Db:
    def __init__(
        self,
        path: Path | str,
        user_id: str,
        shared_threads: bool = False,
        init_schema: bool = True,
        _system: bool = False,
    ) -> None:
        if not user_id and not _system:
            raise ValueError("Db needs a user; use Db.system for auth")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # one request = one connection used by one thread at a time, but FastAPI may hop threads
        self.conn = sqlite3.connect(str(path), check_same_thread=not shared_threads)
        self.user_id = user_id
        if init_schema:
            migrate(self.conn)

    @classmethod
    def system(cls, path: Path | str, shared_threads: bool = False) -> "Db":
        """No user: for auth and migrations only; user rows are not visible through it."""
        return cls(path, user_id="", shared_threads=shared_threads, _system=True)

    def new_conversation(self, now: datetime) -> str:
        cid = f"C-{now:%Y%m%d}-{secrets.token_hex(8)}"
        with self.conn:
            self.conn.execute(
                "insert into conversations (id, started_at, user_id) values (?, ?, ?)",
                (cid, now.isoformat(), self.user_id),
            )
        return cid

    def is_private(self, conv_id: str) -> bool:
        row = self.conn.execute(
            "select 1 from private_conversations where id=? and user_id=?", (conv_id, self.user_id)
        ).fetchone()
        return row is not None

    def mark_private(self, conv_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "insert or ignore into private_conversations (id, user_id) values (?, ?)",
                (conv_id, self.user_id),
            )

    def loaded_toolkits(self, conv_id: str) -> list[str]:
        rows = self.conn.execute(
            "select toolkit from conversation_toolkits where conversation_id=? and user_id=?"
            " order by loaded_at",
            (conv_id, self.user_id),
        ).fetchall()
        return [r[0] for r in rows]

    def add_toolkit(self, conv_id: str, name: str, now: datetime) -> None:
        with self.conn:
            self.conn.execute(
                "insert or ignore into conversation_toolkits"
                " (conversation_id, toolkit, loaded_at, user_id) values (?,?,?,?)",
                (conv_id, name, now.isoformat(), self.user_id),
            )

    def conversation_exists(self, conv_id: str) -> bool:
        row = self.conn.execute(
            "select 1 from conversations where id=? and user_id=?", (conv_id, self.user_id)
        ).fetchone()
        return row is not None

    def add_message(self, conv_id: str, message: dict, now: datetime) -> int:
        if not self.conversation_exists(conv_id):
            raise KeyError("no such conversation")
        with self.conn:
            cur = self.conn.execute(
                "insert into messages (conversation_id, role, body, at, user_id) values (?,?,?,?,?)",
                (conv_id, message["role"], json.dumps(message), now.isoformat(), self.user_id),
            )
            text = message.get("content")
            if message["role"] in ("user", "assistant") and isinstance(text, str) and text:
                self.conn.execute(
                    "insert into message_fts values (?,?,?,?,?,?)",
                    (text, conv_id, cur.lastrowid, message["role"], now.isoformat(), self.user_id),
                )
        return cur.lastrowid

    def messages(self, conv_id: str) -> list[dict]:
        rows = self.conn.execute(
            "select body from messages where conversation_id=? and user_id=? order by id",
            (conv_id, self.user_id),
        ).fetchall()
        return _repair([json.loads(r[0]) for r in rows])

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        words = re.findall(r"\w+", query)
        if not words:
            return []
        match = " ".join(f'"{w}"' for w in words)
        rows = self.conn.execute(
            "select f.conversation_id, f.message_id, f.role,"
            " snippet(message_fts, 0, '[', ']', '…', 12), f.at"
            " from message_fts f join conversations c on c.id = f.conversation_id"
            " where message_fts match ? and f.user_id=? and c.user_id=? order by rank limit ?",
            (match, self.user_id, self.user_id, limit),
        ).fetchall()
        return [SearchHit(*r) for r in rows]

    def conversations_on(self, day: date) -> list[str]:
        rows = self.conn.execute(
            "select distinct conversation_id from messages where at like ? and user_id=? order by 1",
            (f"{day.isoformat()}%", self.user_id),
        ).fetchall()
        return [r[0] for r in rows]

    def add_pending(
        self, kind: str, payload: dict, source: str | None, now: datetime, key: str | None = None
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "insert into pending (kind, payload, source, norm_key, created_at, user_id)"
                " values (?,?,?,?,?,?)",
                (kind, json.dumps(payload), source, key, now.isoformat(), self.user_id),
            )
        return cur.lastrowid

    def list_pending(self, status: str = "pending") -> list[PendingItem]:
        rows = self.conn.execute(
            "select id, kind, payload, source, status, created_at from pending"
            " where status=? and user_id=? order by id",
            (status, self.user_id),
        ).fetchall()
        return [PendingItem(r[0], r[1], json.loads(r[2]), r[3], r[4], r[5]) for r in rows]

    def get_pending(self, item_id: int) -> PendingItem | None:
        rows = self.conn.execute(
            "select id, kind, payload, source, status, created_at from pending"
            " where id=? and user_id=?",
            (item_id, self.user_id),
        ).fetchall()
        r = rows[0] if rows else None
        return PendingItem(r[0], r[1], json.loads(r[2]), r[3], r[4], r[5]) if r else None

    def set_pending_payload(self, item_id: int, payload: dict) -> None:
        with self.conn:
            self.conn.execute(
                "update pending set payload=? where id=? and user_id=?",
                (json.dumps(payload), item_id, self.user_id),
            )

    def set_pending_status(self, item_id: int, status: Literal["approved", "rejected"]) -> None:
        with self.conn:
            self.conn.execute(
                "update pending set status=? where id=? and user_id=?",
                (status, item_id, self.user_id),
            )

    def list_conversations(self, limit: int = 100) -> list[ConversationRow]:
        rows = self.conn.execute(
            "select c.id, c.started_at,"
            " coalesce((select max(at) from messages m"
            "  where m.conversation_id=c.id and m.user_id=c.user_id), c.started_at),"
            " (select json_extract(body, '$.content') from messages m"
            "  where m.conversation_id=c.id and m.user_id=c.user_id and m.role='user'"
            "  order by m.id limit 1)"
            " from conversations c where c.user_id=? order by 3 desc, c.id desc limit ?",
            (self.user_id, limit),
        ).fetchall()
        return [
            ConversationRow(r[0], " ".join(str(r[3] or "").split())[:60] or "New chat", r[1], r[2])
            for r in rows
        ]

    def add_activity(
        self, kind: str, text: str, now: datetime, conversation_id: str | None = None
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "insert into activity (at, kind, text, conversation_id, user_id) values (?,?,?,?,?)",
                (now.isoformat(), kind, text, conversation_id, self.user_id),
            )
        return cur.lastrowid

    def list_activity(self, limit: int = 200) -> list[ActivityRow]:
        rows = self.conn.execute(
            "select id, at, kind, text, conversation_id from activity where user_id=?"
            " order by id desc limit ?",
            (self.user_id, limit),
        ).fetchall()
        return [ActivityRow(*r) for r in rows]

    def get_state(self, key: str) -> str | None:
        r = self.conn.execute(
            "select value from app_state where key=? and user_id=?", (key, self.user_id)
        ).fetchone()
        return r[0] if r else None

    def set_state(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "insert into app_state (user_id, key, value) values (?, ?, ?)"
                " on conflict(user_id, key) do update set value=excluded.value",
                (self.user_id, key, value),
            )

    def new_intake_job(
        self, kind: Literal["documents", "memory", "onboarding"], now: datetime
    ) -> str:
        job_id = f"I-{now:%Y%m%d}-{secrets.token_hex(8)}"
        with self.conn:
            self.conn.execute(
                "insert into intake_jobs (id, kind, status, created_at, user_id) values (?,?,?,?,?)",
                (job_id, kind, "queued", now.isoformat(), self.user_id),
            )
        return job_id

    def update_intake_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        step: str | None = None,
        message: str | None = None,
        result: dict | None = None,
    ) -> None:
        sets = {"status": status, "step": step, "message": message}
        if result is not None:
            sets["result"] = json.dumps(result)
        sets = {k: v for k, v in sets.items() if v is not None}
        if not sets:
            return
        with self.conn:
            self.conn.execute(
                f"update intake_jobs set {', '.join(f'{k}=?' for k in sets)} where id=? and user_id=?",
                (*sets.values(), job_id, self.user_id),
            )

    def get_intake_job(self, job_id: str) -> IntakeJob | None:
        r = self.conn.execute(
            "select id, kind, status, step, message, result, created_at from intake_jobs"
            " where id=? and user_id=?",
            (job_id, self.user_id),
        ).fetchone()
        return IntakeJob(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6]) if r else None

    def running_intake_job(self) -> str | None:
        r = self.conn.execute(
            "select id from intake_jobs where status in ('queued','running') and user_id=? limit 1",
            (self.user_id,),
        ).fetchone()
        return r[0] if r else None

    def fail_interrupted_intake_jobs(self) -> int:
        with self.conn:
            cur = self.conn.execute(
                "update intake_jobs set status='failed', message='interrupted'"
                " where status in ('queued','running')"
            )
        return cur.rowcount

    def pending_exists(self, kind: str, key: str) -> bool:
        row = self.conn.execute(
            "select 1 from pending where kind=? and norm_key=? and user_id=?"
            " and status in ('pending', 'rejected')",
            (kind, key, self.user_id),
        ).fetchone()
        return row is not None


def _repair(messages: list[dict]) -> list[dict]:
    """Give every tool call a result so an interrupted turn can still be sent to a model."""
    out: list[dict] = []
    i = 0
    while i < len(messages):
        m = messages[i]
        out.append(m)
        i += 1
        if m.get("role") == "assistant" and m.get("tool_calls"):
            answered: set[str] = set()
            while i < len(messages) and messages[i].get("role") == "tool":
                answered.add(messages[i]["tool_call_id"])
                out.append(messages[i])
                i += 1
            for call in m["tool_calls"]:
                if call["id"] not in answered:
                    out.append(_interrupted(call["id"]))
    return out


INTERRUPTED = "interrupted: no result recorded"


def _interrupted(call_id: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": INTERRUPTED}
