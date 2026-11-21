from fastapi.testclient import TestClient

from server.agent.adapters.base import Reply
from tests.conftest import add_account


def test_third_chat_turn_is_refused_per_account(make_client, cfg):
    a = make_client([Reply(text="hi")] * 2)
    a.app_state.turns_by_user[cfg.user_id] = 2  # two turns of this account are still answering
    r = a.post("/api/chat", json={"text": "hello"})
    assert r.status_code == 429
    assert r.json()["detail"] == "Another chat is still answering. Try again in a moment."
    b = TestClient(a.app, base_url="http://localhost")
    b.cookies.set("ka_session", add_account(cfg, "u_b"))
    with b.stream("POST", "/api/chat", json={"text": "hello"}) as ok:
        assert ok.status_code == 200
