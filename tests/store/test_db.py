from datetime import UTC, date, datetime

from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0, tzinfo=UTC)


def test_messages_roundtrip_and_fts_finds_words_in_any_role():
    db = Db(":memory:")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "I prefer remote roles"}, NOW)
    db.add_message(cid, {"role": "assistant", "content": "Noted, remote it is"}, NOW)
    assert [m["role"] for m in db.messages(cid)] == ["user", "assistant"]
    hits = db.search("remote")
    assert {h.role for h in hits} == {"user", "assistant"}
    assert all(h.conversation_id == cid for h in hits)
    assert db.conversations_on(date(2031, 4, 5)) == [cid]
    assert db.conversations_on(date(2031, 4, 6)) == []


def test_search_survives_fts_syntax_in_query():
    db = Db(":memory:")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "hello world"}, NOW)
    assert db.search('" OR *') == []
    assert len(db.search("hello")) == 1


def test_interrupted_tool_calls_are_repaired_on_read():
    db = Db(":memory:")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "go"}, NOW)
    calls = [
        {"id": "a", "type": "function", "function": {"name": "get_profile", "arguments": "{}"}},
        {"id": "b", "type": "function", "function": {"name": "get_jobs", "arguments": "{}"}},
    ]
    db.add_message(cid, {"role": "assistant", "content": None, "tool_calls": calls}, NOW)
    db.add_message(cid, {"role": "tool", "tool_call_id": "a", "content": "{}"}, NOW)
    msgs = db.messages(cid)
    tool_ids = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    assert tool_ids == ["a", "b"]
    assert "interrupted" in msgs[-1]["content"]


def test_pending_queue_roundtrip_and_dedupe():
    db = Db(":memory:")
    pid = db.add_pending("memory", {"text": "likes tea"}, "C-1", NOW, key="likes tea")
    assert db.pending_exists("memory", "likes tea")
    [item] = db.list_pending()
    assert item.id == pid and item.payload == {"text": "likes tea"} and item.source == "C-1"
    db.set_pending_status(pid, "rejected")
    # a rejected item still counts as seen, so the next extraction does not queue it again
    assert db.list_pending() == [] and db.pending_exists("memory", "likes tea")


def test_tool_output_is_not_searchable():
    db = Db(":memory:")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "tool", "tool_call_id": "a", "content": "Corner Cafe -4.50"}, NOW)
    assert db.search("Corner") == []
