import json

from server.api.describe import describe_call


def test_describe_call_counts_rows_and_never_echoes_args():
    kind, text = describe_call(
        "search_transactions", {"query": "SECRET-123"}, json.dumps([{"a": 1}, {"a": 2}, {"a": 3}])
    )
    assert kind == "read" and "3 rows" in text and "SECRET-123" not in text
    kind, text = describe_call("propose_change", {"x": "SECRET-123"}, "committed abc1234")
    assert kind == "change" and "SECRET-123" not in text
    assert describe_call("unknown_tool", {}, "not json")[0] == "read"
