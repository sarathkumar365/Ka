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


def test_describe_call_counts_rows_inside_objects_and_labels_search():
    _, text = describe_call(
        "search_transactions", {}, json.dumps({"rows": [{}, {}], "total_matches": 2})
    )
    assert "2 rows" in text
    _, text = describe_call("search", {}, json.dumps({"hits": [{}], "truncated": False}))
    assert "1 row" in text and "Used" not in text
    assert "Used" not in describe_call("finance_coverage", {}, "{}")[1]
