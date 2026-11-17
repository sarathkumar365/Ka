import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app


def client_for(cfg, intake=True) -> TestClient:
    cfg = cfg.model_copy(update={"flags": {"intake": intake}})
    return TestClient(create_app(cfg, lambda: FakeAdapter([])), base_url="http://localhost")


@pytest.fixture
def empty_repo(cfg):
    (cfg.data_repo / "jobs.yaml").write_text("domains: []\njobs: []\n")
    return cfg


def status(c):
    r = c.get("/api/onboarding/status")
    assert r.status_code == 200
    return r.json()


def test_first_run_when_flag_on_repo_empty_and_not_done(empty_repo):
    assert status(client_for(empty_repo)) == {"needed": True, "reason": "first_run"}


def test_flag_off_never_needs_onboarding(empty_repo):
    assert status(client_for(empty_repo, intake=False)) == {"needed": False, "reason": "off"}


def test_existing_data_never_needs_onboarding(cfg):
    assert status(client_for(cfg)) == {"needed": False, "reason": "has_data"}


def test_complete_persists_and_status_flips(empty_repo):
    c = client_for(empty_repo)
    assert c.post("/api/onboarding/complete").json() == {"ok": True}
    assert c.post("/api/onboarding/complete").status_code == 200  # idempotent
    assert status(c) == {"needed": False, "reason": "done"}
    assert status(client_for(empty_repo)) == {
        "needed": False,
        "reason": "done",
    }  # survives a restart


def test_unreadable_repo_does_not_trap_the_owner(empty_repo):
    (empty_repo.data_repo / "profile.yaml").unlink()
    assert status(client_for(empty_repo)) == {"needed": False, "reason": "unavailable"}
