"""Schema before migrations existed (2026-11-17), for upgrade tests."""

OLD_SCHEMA = """
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
