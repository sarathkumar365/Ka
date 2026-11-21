import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.loops.builtin import ensure_builtin_tasks
from server.loops.tasks import TaskStore
from server.store.db import Db
from tests.api.conftest import NOW
from tests.conftest import add_account

TASK = {"name": "Spending check", "brief": "check my spending this week",
        "trigger": {"type": "cron", "hour": 8, "minute": 0, "day_of_week": "mon"}, "toolkits": ["finance"]}


@pytest.fixture
def loops_client(cfg):
    on = cfg.model_copy(update={"flags": {"loops": True}})
    c = TestClient(create_app(on, lambda: FakeAdapter([])), base_url="http://localhost")
    c.cookies.set("ka_session", add_account(on))
    ensure_builtin_tasks(TaskStore(Db(on.db_path, on.user_id)), NOW)
    return c


def test_loops_404_when_flag_off(make_client):
    assert make_client().get("/api/loops").status_code == 404


def test_create_list_pause_and_delete(loops_client):
    c = loops_client
    made = c.post("/api/loops", json=TASK).json()
    assert made["created_by"] == "ui" and made["mode"] == "shadow"
    rows = {t["id"]: t for t in c.get("/api/loops").json()}
    assert set(rows) == {made["id"], "avery:statement_import"}
    assert rows[made["id"]]["last_run"] is None and rows[made["id"]]["approved"] == 0
    assert c.patch(f"/api/loops/{made['id']}", json={"status": "paused", "mode": "direct"}).json()["status"] == "paused"
    assert c.delete(f"/api/loops/{made['id']}").status_code == 200
    assert [t["id"] for t in c.get("/api/loops").json()] == ["avery:statement_import"]


def test_bad_trigger_is_refused(loops_client):
    bad = {**TASK, "trigger": {"type": "interval", "minutes": 1}}
    assert loops_client.post("/api/loops", json=bad).status_code == 422


def test_builtin_cannot_be_deleted(loops_client):
    assert loops_client.delete("/api/loops/avery:statement_import").status_code == 409


def test_pause_switch_round_trip(loops_client):
    c = loops_client
    assert c.put("/api/loops/paused", json={"paused": True}).status_code == 200
    assert c.get("/api/settings").json()["loops_paused"] is True
    c.put("/api/loops/paused", json={"paused": False})
    assert c.get("/api/settings").json()["loops_paused"] is False


def test_runs_listed_and_in_activity(loops_client, cfg):
    c = loops_client
    made = c.post("/api/loops", json={**TASK, "toolkits": []}).json()
    c.put("/api/loops/paused", json={"paused": True})
    started = c.post(f"/api/loops/{made['id']}/run")
    assert started.status_code == 202 and started.json() == {"started": True}
    import time

    for _ in range(100):  # the run happens on its own thread now
        runs = c.get(f"/api/loops/{made['id']}/runs").json()
        if runs:
            break
        time.sleep(0.02)
    assert runs[0]["status"] == "skipped"
    assert any(a["kind"] == "loop" for a in c.get("/api/activity").json())


def test_eleventh_active_loop_is_refused(loops_client):
    c = loops_client
    for n in range(10):
        assert c.post("/api/loops", json={**TASK, "name": f"T{n}", "toolkits": []}).status_code == 200
    r = c.post("/api/loops", json={**TASK, "name": "T10", "toolkits": []})
    assert r.status_code == 409 and r.json()["detail"] == "You have 10 active loops. Pause one first."


def test_run_now_refuses_while_running(loops_client, cfg, monkeypatch):
    import threading

    from server.loops import service

    release = threading.Event()
    real = service.execute

    def slow(*a, **k):
        release.wait(5)

    monkeypatch.setattr(service, "_run", slow)
    c = loops_client
    made = c.post("/api/loops", json={**TASK, "toolkits": []}).json()
    assert c.post(f"/api/loops/{made['id']}/run").status_code == 202
    second = c.post(f"/api/loops/{made['id']}/run")
    release.set()
    assert second.status_code == 409 and second.json()["detail"] == "This loop is already running."
    assert real is service.execute


def test_run_now_names_the_loop_that_is_running(loops_client, monkeypatch):
    import threading

    from server.loops import service

    release = threading.Event()
    monkeypatch.setattr(service, "_run", lambda *a, **k: release.wait(5))
    c = loops_client
    a = c.post("/api/loops", json={**TASK, "name": "A", "toolkits": []}).json()
    b = c.post("/api/loops", json={**TASK, "name": "B", "toolkits": []}).json()
    assert c.post(f"/api/loops/{a['id']}/run").status_code == 202
    import time

    for _ in range(100):  # the run starts on its own thread
        if service._running:
            break
        time.sleep(0.01)
    other = c.post(f"/api/loops/{b['id']}/run")
    release.set()
    assert other.status_code == 409 and other.json()["detail"] == "Another loop is running. Try again when it finishes."
