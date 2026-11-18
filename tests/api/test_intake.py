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
    return client.post("/api/intake/onboarding", files=files)


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


def test_memory_items_are_validated(on):
    c = on()
    empty = [{"text": "", "source": "claude"}]
    assert send(c, files=0, memory=empty).status_code == 422
    too_many = [{"text": "x", "source": f"s{n}"} for n in range(6)]
    assert send(c, files=0, memory=too_many).status_code == 422
    assert send(c, files=0, basics="not json").status_code == 422
    assert c.get("/api/intake/I-nope").status_code == 404


def send(client, files=1, basics=None, memory=None):
    parts = [
        ("files", (f"r{i}.txt", b"Avery Quinn. Globex Corp, Engineer, 2024-02.", "text/plain"))
        for i in range(files)
    ]
    data = {}
    if basics is not None:
        data["basics"] = json.dumps(basics)
    if memory is not None:
        data["memory"] = json.dumps(memory)
    return client.post("/api/intake/onboarding", files=parts or None, data=data)


def test_onboarding_send_starts_one_job(on, cfg):
    c = on()
    r = send(c, basics={"name": "Avery Q"}, memory=[{"source": "claude", "text": "x"}])
    assert r.status_code == 200
    job = wait_done(c, r.json()["job_id"])
    assert job["kind"] == "onboarding" and job["status"] == "done", job
    assert [p["label"] for p in job["result"]["parts"]] == ["Basics", "r0.txt", "claude"]
    assert any(x.get("section") == "basics" for x in c.get("/api/pending").json())


def test_onboarding_send_needs_something(on):
    c = on()
    assert send(c, files=0).status_code == 400
    assert send(c, files=0, basics={"name": "x"}, memory="not a list").status_code == 422


def test_onboarding_send_while_running_is_409(on, cfg):
    c = on()
    db = Db(cfg.db_path)
    db.update_intake_job(db.new_intake_job("documents", datetime.now()), status="running")
    assert send(c).status_code == 409


def test_onboarding_send_oversize_refused_early(on):
    c = on()
    r = c.post(
        "/api/intake/onboarding",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=b", "content-length": str(10**9)},
    )
    assert r.status_code == 413
