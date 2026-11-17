import json
from datetime import UTC, date, datetime

from server.agent.adapters import FakeAdapter, Reply
from server.integrations.data_repo.loader import load_data
from server.memory.extract import extract_memories
from server.store.db import Db
from tests.conftest import FIXTURE

NOW = datetime(2031, 4, 5, 22, 0, tzinfo=UTC)
DAY = date(2031, 4, 5)


def conversation(db, tool_name=None, tool_result=""):
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "I moved to Lisbon and I like tea"}, NOW)
    if tool_name:
        call = {"id": "t1", "type": "function", "function": {"name": tool_name, "arguments": "{}"}}
        db.add_message(cid, {"role": "assistant", "content": None, "tool_calls": [call]}, NOW)
        db.add_message(cid, {"role": "tool", "tool_call_id": "t1", "content": tool_result}, NOW)
    db.add_message(cid, {"role": "assistant", "content": "Noted."}, NOW)
    return cid


def reply(items):
    return Reply(text="Here you go:\n```json\n" + json.dumps(items) + "\n```")


def test_extract_queues_new_fact_and_skips_duplicates():
    db = Db(":memory:")
    cid = conversation(db)
    items = [
        {"type": "fact", "text": "Lives in Lisbon", "replaces": None},
        {"type": "preference", "text": "prefers remote roles", "replaces": None},
    ]
    n = extract_memories(DAY, db, load_data(FIXTURE), FakeAdapter([reply(items)]), NOW)
    assert n == 1
    [item] = db.list_pending()
    assert item.payload["text"] == "Lives in Lisbon" and item.source == cid


def test_extract_bad_json_queues_nothing():
    db = Db(":memory:")
    conversation(db)
    adapter = FakeAdapter([Reply(text="sorry, no json")])
    assert extract_memories(DAY, db, load_data(FIXTURE), adapter, NOW) == 0
    assert db.list_pending() == []


def test_extract_never_sends_finance_tool_output():
    for tool in ("search_transactions", "import_statement"):
        db = Db(":memory:")
        conversation(db, tool, "SECRET-ROW Corner Cafe -4.50")
        adapter = FakeAdapter([reply([])])
        extract_memories(DAY, db, load_data(FIXTURE), adapter, NOW)
        sent = json.dumps(adapter.calls)
        assert "SECRET-ROW" not in sent and "Lisbon" in sent


def test_extract_contradiction_queues_with_replaces():
    db = Db(":memory:")
    conversation(db)
    items = [{"type": "preference", "text": "Prefers hybrid roles", "replaces": "M-0001"}]
    extract_memories(DAY, db, load_data(FIXTURE), FakeAdapter([reply(items)]), NOW)
    assert db.list_pending()[0].payload["replaces"] == "M-0001"


def test_retry_skips_conversations_already_extracted(ctx):
    from datetime import date, datetime

    from server.agent.adapters import AdapterError
    from server.agent.adapters.base import Reply
    from server.integrations.data_repo.loader import load_data
    from server.memory.extract import extract_memories
    from server.store.db import Db

    db = Db(":memory:")
    at = datetime(2031, 4, 9, 10, 0)
    a, b = db.new_conversation(at), db.new_conversation(at)
    for c in (a, b):
        db.add_message(c, {"role": "user", "content": "hello"}, at)

    class Flaky:
        def __init__(self, fail_on):
            self.calls, self.fail_on = 0, fail_on

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls in self.fail_on:
                raise AdapterError("timeout")
            return Reply(text="[]")

    first = Flaky({2})
    data = load_data(ctx.config.data_repo)
    try:
        extract_memories(date(2031, 4, 9), db, data, first, at)
    except AdapterError:
        pass
    second = Flaky(set())
    extract_memories(date(2031, 4, 9), db, data, second, at)
    assert second.calls == 1


def test_private_conversation_routing_and_number_guard(ctx):
    from datetime import date, datetime

    from server.agent.adapters.base import Reply
    from server.integrations.data_repo.loader import load_data
    from server.memory.extract import extract_memories
    from server.store.db import Db

    db = Db(":memory:")
    at = datetime(2031, 4, 9, 10, 0)
    cid = db.new_conversation(at)
    db.add_message(cid, {"role": "user", "content": "what did I spend"}, at)
    db.mark_private(cid)

    class Count:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            return Reply(
                text='[{"type": "fact", "text": "Pays 2100 a month rent"},'
                ' {"type": "fact", "text": "Prefers the credit union"}]'
            )

    default, private = Count(), Count()
    data = load_data(ctx.config.data_repo)
    n = extract_memories(date(2031, 4, 9), db, data, default, at, private_adapter=private)
    assert default.calls == 0 and private.calls == 1
    assert n == 1  # the item with a number from a private chat is dropped
