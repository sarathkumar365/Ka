from server.agent.context import compact_history


def U(t):
    return {"role": "user", "content": t}


def A(t):
    return {"role": "assistant", "content": t}


def A_call(name, cid):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": "{}"}}]}


def T(cid, text):
    return {"role": "tool", "tool_call_id": cid, "content": text}


def test_old_web_results_are_compacted():
    msgs = [U("q1"), A_call("web_search", "w1"), T("w1", "<untrusted>big</untrusted>"), A("a1"),
            U("q2"), A_call("web_search", "w2"), T("w2", "fresh")]
    out = compact_history(msgs, current_turn_start=4)
    assert "big" not in out[2]["content"] and out[2]["tool_call_id"] == "w1"
    assert out[6]["content"] == "fresh"
    assert msgs[2]["content"] == "<untrusted>big</untrusted>"  # stored history untouched


def test_other_tool_results_are_kept():
    msgs = [U("q1"), A_call("get_profile", "p1"), T("p1", "Avery"), A("a1"), U("q2")]
    assert compact_history(msgs, current_turn_start=4)[2]["content"] == "Avery"
