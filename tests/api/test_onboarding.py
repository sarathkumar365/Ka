from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.store.db import Db


def client_for(cfg, intake=True) -> TestClient:
    cfg = cfg.model_copy(update={"flags": {"intake": intake}})
    return TestClient(create_app(cfg, lambda: FakeAdapter([])), base_url="http://localhost")


@pytest.fixture
def empty_repo(cfg):
    root = cfg.data_repo
    (root / "jobs.yaml").write_text("domains: []\njobs: []\n")
    (root / "profile.yaml").write_text('name: ""\n')
    (root / "education.yaml").write_text("entries: []\n")
    (root / "memory.yaml").write_text("entries: []\n")
    return cfg


def status(c):
    r = c.get("/api/onboarding/status")
    assert r.status_code == 200
    return r.json()


def test_first_run_when_repo_empty(empty_repo):
    assert status(client_for(empty_repo)) == {"needed": True, "reason": "first_run"}


def test_flag_off_never_needs_onboarding(empty_repo):
    assert status(client_for(empty_repo, intake=False)) == {"needed": False, "reason": "off"}


def test_existing_data_never_needs_onboarding(cfg):
    assert status(client_for(cfg)) == {"needed": False, "reason": "has_data"}


def test_a_name_alone_counts_as_data(empty_repo):
    (empty_repo.data_repo / "profile.yaml").write_text('name: "Avery"\n')
    assert status(client_for(empty_repo)) == {"needed": False, "reason": "has_data"}


def test_cards_waiting_in_pending_hold_the_redirect_until_decided(empty_repo):
    c = client_for(empty_repo)
    db = Db(empty_repo.db_path)
    card = db.add_pending("bundle", {"section": "basics"}, "onboarding", datetime.now())
    assert status(c) == {"needed": False, "reason": "pending"}
    db.set_pending_status(card, "rejected")  # rejected everything: still nothing known
    assert status(c) == {"needed": True, "reason": "first_run"}


def test_unreadable_repo_does_not_trap_the_owner(empty_repo):
    (empty_repo.data_repo / "profile.yaml").unlink()
    assert status(client_for(empty_repo)) == {"needed": False, "reason": "unavailable"}


def test_finance_cards_do_not_hold_the_redirect(empty_repo):
    db = Db(empty_repo.db_path)
    db.add_pending("statement", {}, "drive", datetime.now())
    db.add_pending("bundle", {"section": "categories"}, "suggest", datetime.now())
    assert status(client_for(empty_repo)) == {"needed": True, "reason": "first_run"}


def test_a_running_onboarding_job_holds_the_redirect(empty_repo):
    c = client_for(empty_repo)  # startup fails interrupted jobs, so start the job after it
    db = Db(empty_repo.db_path)
    db.update_intake_job(db.new_intake_job("onboarding", datetime.now()), status="running")
    assert status(c) == {"needed": False, "reason": "pending"}
