import json
import threading
import time

from server.agent.adapters import AdapterError
from server.agent.adapters.base import Reply, ToolCall
from tests.conftest import git

PATCH = json.dumps({"target": "account", "op": "update", "key": "A-01", "fields": {"label": "Zed"}})


def frames(client, body):
    """POST /api/chat and return [(event, data)]. TestClient buffers the whole stream."""
    out = []
    with client.stream("POST", "/api/chat", json=body) as r:
        assert r.status_code == 200
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                out.append((event, json.loads(line[6:])))
    return out


def answer_approvals(client, approve, results):
    """Stand-in for the browser: answer every approval twice, record both status codes."""
    broker = client.app_state.broker

    def run():
        deadline = time.time() + 5
        while time.time() < deadline:
            for i in broker.open_ids():
                a = client.post(f"/api/approvals/{i}", json={"approve": approve}).status_code
                b = client.post(f"/api/approvals/{i}", json={"approve": approve}).status_code
                results.append((a, b))
                return
            time.sleep(0.01)

    t = threading.Thread(target=run)
    t.start()
    return t


def test_answer_turn_streams_events_in_order(make_client, db):
    replies = [Reply(tool_calls=[ToolCall("1", "get_profile", "{}")]), Reply(text="Hello there")]
    names = [e for e, _ in frames(make_client(replies), {"text": "who am I?"})]
    assert names == ["conversation", "tool_call", "tool_result", "answer", "done"]
    [conv] = db.list_conversations()
    assert [m["role"] for m in db.messages(conv.id)] == ["user", "assistant", "tool", "assistant"]
    assert [a.kind for a in db.list_activity()] == ["read"]


def test_approval_applied_once_and_second_answer_is_404(make_client, cfg):
    before = int(git(cfg.data_repo, "rev-list", "--count", "HEAD"))
    client = make_client(
        [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="ok")]
    )
    results: list = []
    t = answer_approvals(client, True, results)
    ev = frames(client, {"text": "relabel"})
    t.join()
    assert results == [(200, 404)]
    assert "approval" in [e for e, _ in ev]
    assert int(git(cfg.data_repo, "rev-list", "--count", "HEAD")) == before + 1


def test_declined_approval_changes_nothing(make_client, cfg):
    before = git(cfg.data_repo, "rev-list", "--count", "HEAD")
    client = make_client(
        [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="ok")]
    )
    t = answer_approvals(client, False, [])
    ev = frames(client, {"text": "relabel"})
    t.join()
    assert git(cfg.data_repo, "rev-list", "--count", "HEAD") == before
    result = next(d for e, d in ev if e == "tool_result")["result"]
    assert "declined" in result


def test_unanswered_approval_times_out_and_declines(make_client, cfg):
    before = git(cfg.data_repo, "rev-list", "--count", "HEAD")
    client = make_client(
        [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="ok")],
        approval_timeout=0.2,
    )
    ev = frames(client, {"text": "relabel"})
    assert ev[-1][0] == "done"
    assert git(cfg.data_repo, "rev-list", "--count", "HEAD") == before


def test_provider_error_becomes_error_event_and_chat_stays_usable(make_client, db):
    class Down:
        def complete(self, messages, tools):
            raise AdapterError("provider reports no credits remaining")

    client = make_client(factory=Down)
    ev = frames(client, {"text": "hi"})
    assert ev[1][0] == "error" and "no credits" in ev[1][1]["message"]
    [conv] = db.list_conversations()
    assert db.messages(conv.id)[0]["content"] == "hi"
    ev2 = frames(client, {"conversation_id": conv.id, "text": "again"})
    assert ev2[-1][0] == "done"


def test_unknown_conversation_404_and_running_conversation_409(make_client, db):
    client = make_client()
    assert (
        client.post("/api/chat", json={"conversation_id": "C-nope", "text": "x"}).status_code == 404
    )
    cid = db.new_conversation(__import__("datetime").datetime.now())
    client.app_state.running.add(cid)
    assert client.post("/api/chat", json={"conversation_id": cid, "text": "x"}).status_code == 409


def test_closing_the_stream_mid_approval_frees_the_conversation_quickly(make_client):
    """Disconnect must cancel the waiting approval, not wait out the 600 s timeout."""
    import asyncio

    client = make_client(
        [Reply(tool_calls=[ToolCall("1", "propose_change", PATCH)]), Reply(text="ok")],
        approval_timeout=30,
    )
    app, state = client.app, client.app_state
    body = json.dumps({"text": "relabel"}).encode()

    async def scenario():
        seen, gone = asyncio.Event(), asyncio.Event()
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and b"approval" in message.get("body", b""):
                seen.set()

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "raw_path": b"/api/chat",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "http_version": "1.1",
            "server": ("localhost", 80),
            "client": ("127.0.0.1", 1),
            "headers": [
                (b"host", b"localhost"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
        task = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(seen.wait(), 5)
        gone.set()
        for _ in range(40):  # up to 4 s, far below the 30 s approval timeout
            if not state.running:
                break
            await asyncio.sleep(0.1)
        await asyncio.wait_for(task, 5)
        return not state.running

    assert asyncio.run(scenario())
