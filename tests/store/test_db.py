from datetime import UTC, date, datetime

from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0, tzinfo=UTC)


def test_messages_roundtrip_and_fts_finds_words_in_any_role():
    db = Db(":memory:", "avery")
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
    db = Db(":memory:", "avery")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "hello world"}, NOW)
    assert db.search('" OR *') == []
    assert len(db.search("hello")) == 1


def test_interrupted_tool_calls_are_repaired_on_read():
    db = Db(":memory:", "avery")
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
    db = Db(":memory:", "avery")
    pid = db.add_pending("memory", {"text": "likes tea"}, "C-1", NOW, key="likes tea")
    assert db.pending_exists("memory", "likes tea")
    [item] = db.list_pending()
    assert item.id == pid and item.payload == {"text": "likes tea"} and item.source == "C-1"
    db.set_pending_status(pid, "rejected")
    # a rejected item still counts as seen, so the next extraction does not queue it again
    assert db.list_pending() == [] and db.pending_exists("memory", "likes tea")


def test_tool_output_is_not_searchable():
    db = Db(":memory:", "avery")
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "tool", "tool_call_id": "a", "content": "Corner Cafe -4.50"}, NOW)
    assert db.search("Corner") == []


def test_list_conversations_titles_and_orders():
    db = Db(":memory:", "avery")
    old = db.new_conversation(NOW)
    db.add_message(old, {"role": "user", "content": "x" * 200}, NOW)
    new = db.new_conversation(NOW)
    empty = db.new_conversation(NOW)
    later = datetime(2031, 4, 6, tzinfo=UTC)
    db.add_message(new, {"role": "user", "content": "  hello\n there "}, NOW)
    db.add_message(old, {"role": "assistant", "content": "late"}, later)
    rows = {r.id: r for r in db.list_conversations()}
    assert db.list_conversations()[0].id == old
    assert rows[old].title == "x" * 60
    assert rows[new].title == "hello there"
    assert rows[empty].title == "New chat"


def test_activity_newest_first():
    db = Db(":memory:", "avery")
    db.add_activity("read", "first", NOW)
    db.add_activity("change", "second", NOW, "C-1")
    rows = db.list_activity()
    assert [r.text for r in rows] == ["second", "first"]
    assert rows[0].conversation_id == "C-1" and rows[0].kind == "change"


def test_shared_threads_db_can_move_between_threads(tmp_path):
    import threading

    db = Db(tmp_path / "t.db", "avery", shared_threads=True)
    errors = []

    def use():
        try:
            db.list_conversations()
            db.conn.close()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=use)
    t.start()
    t.join()
    assert errors == []


def test_app_state_roundtrip():
    db = Db(":memory:", "avery")
    assert db.get_state("onboarding_done") is None
    db.set_state("onboarding_done", "1")
    assert db.get_state("onboarding_done") == "1"
    db.set_state("onboarding_done", "0")
    assert db.get_state("onboarding_done") == "0"


def test_two_accounts_never_see_each_other(tmp_path):
    import pytest

    when = datetime(2026, 11, 20)
    path = tmp_path / "ka.db"
    a, b = Db(path, "u_a"), Db(path, "u_b")
    ca = a.new_conversation(when)
    a.add_message(ca, {"role": "user", "content": "secret pancakes"}, when)
    a.add_pending("memory", {"text": "x"}, "chat", when)
    assert b.search("pancakes") == [] and b.list_conversations() == [] and b.list_pending() == []
    assert b.messages(ca) == [] and not b.conversation_exists(ca)
    with pytest.raises(KeyError):
        b.add_message(ca, {"role": "user", "content": "hi"}, when)
    assert len(ca.rsplit("-", 1)[1]) == 16
    assert len(a.new_intake_job("documents", when).rsplit("-", 1)[1]) == 16
    hit = a.conn.execute("select user_id from message_fts").fetchone()
    assert hit == ("u_a",)
