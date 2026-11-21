"""Ordered SQLite schema migrations, keyed by `pragma user_version`. Never edit a shipped step."""

import sqlite3
from collections.abc import Callable

BASE = """
create table if not exists conversations (id text primary key, started_at text not null);
create table if not exists messages (
    id integer primary key autoincrement,
    conversation_id text not null references conversations(id),
    role text not null, body text not null, at text not null
);
create index if not exists messages_conv on messages(conversation_id, id);
create virtual table if not exists message_fts using fts5(
    text, conversation_id unindexed, message_id unindexed, role unindexed, at unindexed
);
create table if not exists pending (
    id integer primary key autoincrement,
    kind text not null, payload text not null, source text, norm_key text,
    status text not null default 'pending', created_at text not null
);
create table if not exists private_conversations (id text primary key);
create table if not exists app_state (key text primary key, value text not null);
create table if not exists intake_jobs (
    id text primary key, kind text not null, status text not null,
    step text not null default '', message text not null default '',
    result text not null default '{}', created_at text not null
);
create table if not exists activity (
    id integer primary key autoincrement,
    at text not null, kind text not null, text text not null, conversation_id text
);
"""

USER_TABLES = (
    "conversations", "messages", "pending", "activity", "intake_jobs", "private_conversations",
)  # fmt: skip


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"pragma table_info({table})")}


def _m1_users(conn: sqlite3.Connection) -> None:
    conn.executescript(BASE)
    for table in USER_TABLES:
        if "user_id" not in _columns(conn, table):
            conn.execute(f"alter table {table} add column user_id text not null default ''")
    if "user_id" not in _columns(conn, "app_state"):
        conn.executescript(
            """
            create table app_state_new (
                user_id text not null default '', key text not null, value text not null,
                primary key (user_id, key)
            );
            insert into app_state_new (user_id, key, value) select '', key, value from app_state;
            drop table app_state;
            alter table app_state_new rename to app_state;
            """
        )
    conn.executescript(
        """
        create index if not exists conversations_user on conversations(user_id);
        create index if not exists pending_user on pending(user_id, status);
        create table if not exists users (
            id text primary key, username text unique not null, password_hash text not null,
            created_at text not null, failed_logins integer not null default 0, locked_until text
        );
        create table if not exists sessions (
            token_hash text primary key, user_id text not null references users(id),
            created_at text not null, last_seen text not null,
            expires_at text not null, hard_expires_at text not null, user_agent text
        );
        create table if not exists conversation_toolkits (
            conversation_id text not null, toolkit text not null, loaded_at text not null,
            user_id text not null default '', primary key (conversation_id, toolkit)
        );
        """
    )


def _m2_loops(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists scheduled_tasks (
            id text primary key, user_id text not null, name text not null,
            kind text not null, builtin text, trigger text not null,
            brief text not null default '', toolkits text not null default '[]',
            checks text not null default '[]', limits text not null default '{}',
            mode text not null default 'shadow', status text not null default 'active',
            created_by text not null, created_at text not null, last_checkin text
        );
        create table if not exists task_runs (
            id integer primary key autoincrement, task_id text not null, user_id text not null,
            started_at text not null, finished_at text, status text not null,
            reason text not null default '', model_calls integer not null default 0,
            tool_calls integer not null default 0, cost_usd text not null default '0',
            result text not null default '{}'
        );
        create index if not exists task_runs_task on task_runs(task_id, id);
        create table if not exists task_writes (
            task_id text not null, write_key text not null, run_id integer not null,
            at text not null, user_id text not null default '',
            primary key (task_id, write_key)
        );
        """
    )


STEPS: list[Callable[[sqlite3.Connection], None]] = [_m1_users, _m2_loops]


def migrate(conn: sqlite3.Connection) -> int:
    version = conn.execute("pragma user_version").fetchone()[0]
    for n, step in enumerate(STEPS, start=1):
        if version < n:
            with conn:
                step(conn)
                conn.execute(f"pragma user_version = {n}")
            version = n
    return version


def backfill_user(conn: sqlite3.Connection, user_id: str) -> None:
    """Rows written before accounts existed belong to the first account."""
    with conn:
        for table in (*USER_TABLES, "app_state", "conversation_toolkits"):
            conn.execute(f"update {table} set user_id=? where user_id=''", (user_id,))
