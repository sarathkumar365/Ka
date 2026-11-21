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
    assert c.post(f"/api/loops/{made['id']}/run").status_code == 200
    runs = c.get(f"/api/loops/{made['id']}/runs").json()
    assert runs[0]["status"] == "skipped"
    assert any(a["kind"] == "loop" for a in c.get("/api/activity").json())
