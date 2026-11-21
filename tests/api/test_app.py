from server.integrations.data_repo.loader import load_data
from server.memory.pending import queue_memory
from tests.api.conftest import NOW


def test_foreign_host_rejected(make_client):
    client = make_client()
    assert client.get("/api/conversations", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/conversations").status_code == 200


def test_pending_approve_writes_memory_and_logs_activity(make_client, cfg, db):
    data = load_data(cfg.data_repo)
    queue_memory(db, data, "Prefers short answers", "preference", None, "C-1", NOW)
    client = make_client()
    [item] = client.get("/api/pending").json()
    assert item["text"] == "Prefers short answers" and item["old"] is None
    r = client.post(f"/api/pending/{item['id']}/approve")
    assert r.status_code == 200 and "added" in r.json()["result"]
    assert "Prefers short answers" in [e.text for e in load_data(cfg.data_repo).memory.entries]
    assert client.get("/api/pending").json() == []
    assert "pending" in [a["kind"] for a in client.get("/api/activity").json()]


def test_pending_replaces_shows_old_text_and_conflict_is_409(make_client, cfg, db):
    data = load_data(cfg.data_repo)
    old = next(e for e in data.memory.entries if e.status == "active")
    client = make_client()
    queue_memory(db, data, "Replacement text", "fact", old.id, None, NOW)
    [item] = client.get("/api/pending").json()
    assert item["old"] == old.text
    queue_memory(db, data, "Another fact", "fact", None, None, NOW)
    pid = client.get("/api/pending").json()[-1]["id"]
    assert client.post(f"/api/pending/{pid}/approve").status_code == 200
    assert client.post(f"/api/pending/{pid}/approve").status_code == 409


def test_settings_hides_secrets(make_client, cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRETVALUE")
    text = make_client().get("/api/settings").text
    assert "SECRETVALUE" not in text and str(cfg.data_repo) not in text


def test_conversation_history_merges_tool_calls(make_client, db):
    cid = db.new_conversation(NOW)
    db.add_message(cid, {"role": "user", "content": "hi"}, NOW)
    calls = [{"id": "a", "type": "function", "function": {"name": "get_jobs", "arguments": "{}"}}]
    db.add_message(cid, {"role": "assistant", "content": None, "tool_calls": calls}, NOW)
    db.add_message(cid, {"role": "tool", "tool_call_id": "a", "content": "[]"}, NOW)
    db.add_message(cid, {"role": "assistant", "content": "done"}, NOW)
    client = make_client()
    items = client.get(f"/api/conversations/{cid}").json()["items"]
    assert [i["kind"] for i in items] == ["user", "tool", "assistant"]
    assert items[1]["name"] == "get_jobs" and items[1]["result"] == "[]"
    assert client.get("/api/conversations/C-nope").status_code == 404


def test_ui_routes_fall_back_to_index_but_api_404s_stay_json(make_client, tmp_path, monkeypatch):
    from server.api import app as app_module

    (tmp_path / "index.html").write_text("<html>ka</html>")
    monkeypatch.setattr(app_module, "UI_DIST", tmp_path)
    client = make_client()
    assert "ka" in client.get("/chat/C-1").text
    assert client.get("/api/conversations/C-nope").json()["detail"] == "no such conversation"


def test_cross_site_post_is_refused_but_same_origin_works(make_client, cfg, db):
    data = load_data(cfg.data_repo)
    queue_memory(db, data, "Cross site probe", "fact", None, None, NOW)
    pid = make_client().get("/api/pending").json()[0]["id"]
    client = make_client()
    evil = client.post(f"/api/pending/{pid}/reject", headers={"origin": "https://evil.example"})
    assert evil.status_code == 403
    assert client.get("/api/pending").json()[0]["id"] == pid  # untouched
    ok = client.post(f"/api/pending/{pid}/reject", headers={"origin": "http://localhost"})
    assert ok.status_code == 200


def test_concurrent_double_approve_writes_memory_once(make_client, cfg, db):
    import threading

    data = load_data(cfg.data_repo)
    queue_memory(db, data, "Only once please", "fact", None, None, NOW)
    client = make_client()
    pid = client.get("/api/pending").json()[0]["id"]
    codes: list[int] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        codes.append(client.post(f"/api/pending/{pid}/approve").status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200, 409]
    texts = [e.text for e in load_data(cfg.data_repo).memory.entries]
    assert texts.count("Only once please") == 1
