import json
import time
from datetime import datetime

import pytest

from server.agent.adapters.base import Reply
from server.agent.adapters.fake import FakeAdapter
from server.integrations.data_repo.loader import load_data
from server.store.db import Db
from tests.conftest import git

GOOD = json.dumps(
    {
        "profile": {"name": "Avery Quinn"},
        "domains": ["Robotics"],
        "jobs": [
            {
                "company": "Globex Corp",
                "position": "Engineer",
                "start": "2024-02",
                "highlights": [
                    {"text": "Built a robot arm API", "domains": ["Robotics"]},
                    {"text": "Second"},
                ],
            }
        ],
    }
)


@pytest.fixture
def on(cfg, make_client):
    flagged = cfg.model_copy(update={"flags": {"intake": True}})

    def make(**kw):
        from fastapi.testclient import TestClient

        from server.api.app import create_app

        app = create_app(flagged, lambda: FakeAdapter([Reply(text=GOOD)] * 4), **kw)
        c = TestClient(app, base_url="http://localhost")
        c.cfg = flagged
        return c

    return make


def upload(client, name="resume.txt", content=b"Avery Quinn. Globex Corp, Engineer, 2024-02.", n=1):
    files = [("files", (name if i == 0 else f"{i}{name}", content, "text/plain")) for i in range(n)]
    return client.post("/api/intake/documents", files=files)


def wait_done(client, job_id):
    for _ in range(100):
        j = client.get(f"/api/intake/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_intake_off_returns_404(make_client):
    c = make_client()
    assert upload(c).status_code == 404
    assert c.get("/api/intake/I-1").status_code == 404


def test_upload_runs_job_and_cards_flow_through_pending(on, cfg):
    c = on()
    r = upload(c)
    assert r.status_code == 200
    job = wait_done(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rows = c.get("/api/pending").json()
    bundle = [x for x in rows if x["kind"] == "bundle"]
    sections = [x["section"] for x in bundle]
    assert "domains" in sections and "job" in sections
    jobcard = next(x for x in bundle if x["section"] == "job")
    assert jobcard["ready"] is False
    assert c.post(f"/api/pending/{jobcard['id']}/approve").status_code == 409  # domains first
    dom = next(x for x in bundle if x["section"] == "domains")
    assert c.post(f"/api/pending/{dom['id']}/approve").status_code == 200
    n = int(git(cfg.data_repo, "rev-list", "--count", "HEAD"))
    # approve only the job line and the first highlight
    r = c.post(f"/api/pending/{jobcard['id']}/approve", json={"selected": ["i1", "i2"]})
    assert r.status_code == 200
    assert int(git(cfg.data_repo, "rev-list", "--count", "HEAD")) == n + 1
    saved = next(j for j in load_data(cfg.data_repo).jobs.jobs if j.company == "Globex Corp")
    assert [h.text for h in saved.highlights] == ["Built a robot arm API"]
    assert "Globex" in c.get("/api/activity").json()[0]["text"]


def test_bad_uploads_are_refused_and_cleaned_up(on, cfg):
    c = on()
    assert upload(c, "x.exe", b"MZ").status_code == 400
    assert upload(c, "empty.txt", b"").status_code == 400
    assert upload(c, "big.txt", b"a" * (10 * 1024 * 1024 + 1)).status_code == 400
    assert upload(c, n=6).status_code == 400
    folder = cfg.data_repo / "local" / "intake"
    assert not folder.exists() or not any(folder.rglob("*.*"))


def test_second_job_while_running_is_409(on, cfg):
    c = on()
    db = Db(cfg.db_path)
    db.update_intake_job(db.new_intake_job("documents", datetime.now()), status="running")
    assert upload(c).status_code == 409
    one = {"items": [{"text": "x", "source": "claude"}]}
    assert c.post("/api/intake/memory", json=one).status_code == 409


def test_basics_and_memory_endpoints(on):
    c = on()
    r = c.post(
        "/api/intake/basics",
        json={"name": "Avery Quinn", "city": "Newtown", "role": "Platform engineer"},
    )
    assert r.status_code == 200 and r.json()["cards"] >= 1
    empty = {"items": [{"text": "", "source": "claude"}]}
    assert c.post("/api/intake/memory", json=empty).status_code == 422
    too_many = {"items": [{"text": "x", "source": f"s{n}"} for n in range(6)]}
    assert c.post("/api/intake/memory", json=too_many).status_code == 422
    assert c.post("/api/intake/memory", json={"items": []}).status_code == 422
    assert c.get("/api/intake/I-nope").status_code == 404


def test_oversize_body_is_refused_before_it_is_read(on, cfg):
    c = on()
    r = c.post(
        "/api/intake/documents",
        files=[("files", ("big.txt", b"a" * (52 * 1024 * 1024), "text/plain"))],
    )
    assert r.status_code == 413
