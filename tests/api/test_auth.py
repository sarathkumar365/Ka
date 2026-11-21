import shutil
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters import Reply
from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.config import Config
from server.store.db import Db
from tests.conftest import FIXTURE, git

PW = "correct horse 1"


@pytest.fixture
def fresh(tmp_path):
    """A data repo in the old root layout and no account yet."""
    root = tmp_path / "data"
    shutil.copytree(FIXTURE, root)
    (root / "memory" / "core.yaml").rename(root / "memory.yaml")
    shutil.rmtree(root / "memory")
    (root / ".gitignore").write_text("local/\n.ka.lock\n")
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.test"),
                 ("config", "user.name", "T"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        git(root, *args)
    app = create_app(Config(data_repo=root), lambda: FakeAdapter([]))
    return TestClient(app, base_url="http://localhost")


def test_api_needs_a_session(make_client):
    c = make_client(login=False)
    assert c.get("/api/conversations").status_code == 401
    assert c.get("/api/auth/status").status_code == 200


def test_setup_once_then_closed(fresh):
    status = fresh.get("/api/auth/status").json()
    assert (status["setup_needed"], status["user"], status["min_password"]) == (True, None, 10)
    r = fresh.post("/api/auth/setup", json={"username": "avery", "password": PW})
    assert r.status_code == 200 and "ka_session" in r.cookies
    assert fresh.get("/api/conversations").status_code == 200
    status = fresh.get("/api/auth/status").json()
    assert (status["setup_needed"], status["user"]) == (False, "avery")
    again = fresh.post("/api/auth/setup", json={"username": "blake", "password": "correct horse 2"})
    assert again.status_code == 409


def test_setup_moves_data_and_backfills(fresh):
    fresh.post("/api/auth/setup", json={"username": "avery", "password": PW})
    assert fresh.get("/api/onboarding/status").status_code == 200
    me = fresh.get("/api/settings")
    assert me.status_code == 200


def test_cookie_flags(fresh):
    r = fresh.post("/api/auth/setup", json={"username": "avery", "password": PW})
    header = r.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/" in header
    assert "secure" not in header  # plain http on localhost only


def test_login_wrong_password_and_logout(fresh):
    fresh.post("/api/auth/setup", json={"username": "avery", "password": PW})
    fresh.post("/api/auth/logout")
    assert fresh.get("/api/conversations").status_code == 401
    bad = fresh.post("/api/auth/login", json={"username": "avery", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "wrong username or password"
    ok = fresh.post("/api/auth/login", json={"username": "avery", "password": PW})
    assert ok.status_code == 200 and fresh.get("/api/conversations").status_code == 200


def test_expired_session_is_401(make_client, monkeypatch):
    c = make_client()
    later = datetime.now() + timedelta(days=31)
    monkeypatch.setattr("server.auth.middleware.now", lambda: later)
    assert c.get("/api/conversations").status_code == 401


def test_rows_written_through_api_carry_the_user(make_client, cfg):
    c = make_client([Reply(text="hello")])
    c.post("/api/chat", json={"text": "hi"})
    rows = Db.system(cfg.db_path).conn.execute("select distinct user_id from conversations").fetchall()
    assert rows == [("avery",)]
