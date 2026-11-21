from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters import Reply
from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.config import Config
from server.store.db import Db
from tests.conftest import git

PW = "correct horse 1"


@pytest.fixture
def empty_client(tmp_path):
    """An empty data repo and no accounts yet."""
    root = tmp_path / "data"
    root.mkdir()
    (root / ".gitignore").write_text("local/\n.ka.lock\n")
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.test"),
                 ("config", "user.name", "T"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        git(root, *args)
    app = create_app(Config(data_repo=root), lambda: FakeAdapter([]))
    return TestClient(app, base_url="http://localhost")


def signup(client, username):
    return client.post("/api/auth/signup", json={"username": username, "password": PW})


def test_api_needs_a_session(make_client):
    c = make_client(login=False)
    assert c.get("/api/conversations").status_code == 401
    assert c.get("/api/auth/status").status_code == 200


def test_anyone_can_sign_up_and_accounts_are_separate(empty_client):
    status = empty_client.get("/api/auth/status").json()
    assert (status["user"], status["min_password"]) == (None, 10) and "setup_needed" not in status
    a = signup(empty_client, "avery")
    assert a.status_code == 200 and a.json()["user"].startswith("u_")
    empty_client.cookies.clear()
    b = signup(empty_client, "blake")
    assert b.status_code == 200 and b.json()["user"] != a.json()["user"]
    status = empty_client.get("/api/auth/status").json()
    assert (status["username"], status["user"]) == ("blake", b.json()["user"])
    root = empty_client.app.state.cfg.data_repo
    assert (root / "users" / b.json()["user"] / "profile.yaml").is_file()
    assert empty_client.get("/api/onboarding/status").status_code == 200


def test_taken_username_and_signup_limit(empty_client):
    signup(empty_client, "avery")
    dup = signup(empty_client, "avery")
    assert dup.status_code == 409 and dup.json()["detail"] == "that username is taken"
    codes = [signup(empty_client, f"user{i}x").status_code for i in range(6)]
    assert codes[-1] == 429


def test_cookie_flags(empty_client):
    r = signup(empty_client, "avery")
    header = r.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/" in header
    assert "secure" not in header  # plain http on localhost only


def test_login_wrong_password_and_logout(empty_client):
    signup(empty_client, "avery")
    empty_client.post("/api/auth/logout")
    assert empty_client.get("/api/conversations").status_code == 401
    bad = empty_client.post("/api/auth/login", json={"username": "avery", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "wrong username or password"
    ok = empty_client.post("/api/auth/login", json={"username": "avery", "password": PW})
    assert ok.status_code == 200 and empty_client.get("/api/conversations").status_code == 200


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


def test_lockout_is_per_address_not_per_account(empty_client):
    signup(empty_client, "avery")
    empty_client.cookies.clear()
    empty_client.app.state.trusted_proxies = {"testclient"}  # the test client stands in for the proxy

    def login(password, ip):
        body = {"username": "avery", "password": password}
        return empty_client.post("/api/auth/login", json=body, headers={"x-forwarded-for": ip})

    for _ in range(5):
        assert login("wrong password 1", "10.0.0.9").status_code == 401
    assert login(PW, "10.0.0.9").status_code == 429
    assert login(PW, "10.0.0.7").status_code == 200


def test_another_accounts_ids_are_404(make_client, cfg):
    from tests.conftest import add_account

    a = make_client([Reply(text="hello")])
    a.post("/api/chat", json={"text": "hi"})
    conv = a.get("/api/conversations").json()[0]["id"]
    b = TestClient(a.app, base_url="http://localhost")
    b.cookies.set("ka_session", add_account(cfg, "u_b"))
    assert a.get(f"/api/conversations/{conv}").status_code == 200
    assert b.get(f"/api/conversations/{conv}").status_code == 404
    assert b.post("/api/chat", json={"text": "hi", "conversation_id": conv}).status_code == 404


def test_forged_forwarded_address_does_not_lock_others(empty_client):
    signup(empty_client, "avery")
    empty_client.cookies.clear()
    empty_client.app.state.trusted_proxies = {"testclient"}
    body = {"username": "avery", "password": "wrong password 1"}
    for _ in range(5):  # the attacker claims the victim's address; the proxy appends its own
        empty_client.post("/api/auth/login", json=body, headers={"x-forwarded-for": "10.0.0.5, 10.0.0.66"})
    ok = empty_client.post("/api/auth/login", json={"username": "avery", "password": PW},
                           headers={"x-forwarded-for": "10.0.0.5"})
    assert ok.status_code == 200
