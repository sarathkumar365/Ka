import json
import stat

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.config import GoogleConfig
from server.integrations.google.oauth import GoogleAuth, GoogleAuthError
from tests.conftest import add_account


def gcfg(tmp_path):
    client = tmp_path / "client.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "id.apps.googleusercontent.com",
                    "client_secret": "s",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
    )
    return GoogleConfig(client_file=client)


def test_missing_or_unrefreshable_token_raises_reconnect(tmp_path, monkeypatch):
    auth = GoogleAuth(gcfg(tmp_path), tmp_path / "google" / "token.json")
    with pytest.raises(GoogleAuthError, match="reconnect Google"):
        auth.credentials()
    (tmp_path / "google").mkdir()
    (tmp_path / "google" / "token.json").write_text(
        json.dumps(
            {
                "token": "old",
                "refresh_token": "r",
                "client_id": "id",
                "client_secret": "s",
                "token_uri": "https://oauth2.googleapis.com/token",
                "expiry": "2000-01-01T00:00:00Z",
            }
        )
    )
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    def refuse(self, request):
        raise RefreshError("invalid_grant")

    monkeypatch.setattr(Credentials, "refresh", refuse)
    with pytest.raises(GoogleAuthError, match="reconnect Google"):
        auth.credentials()


def test_token_written_with_mode_0600(tmp_path):
    class Creds:
        def to_json(self):
            return '{"token": "t"}'

    path = tmp_path / "google" / "token.json"
    GoogleAuth(gcfg(tmp_path), path).save(Creds())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.fixture
def make_client_google(ctx, tmp_path):
    def make():
        cfg = ctx.config.model_copy(update={"flags": {"google": True}, "google": gcfg(tmp_path)})
        c = TestClient(create_app(cfg, lambda: FakeAdapter([])), base_url="http://localhost")
        c.cookies.set("ka_session", add_account(cfg))
        return c

    return make


def test_callback_rejects_wrong_state(ctx, tmp_path):
    cfg = ctx.config.model_copy(update={"flags": {"google": True}, "google": gcfg(tmp_path)})
    c = TestClient(create_app(cfg, lambda: FakeAdapter([])), base_url="http://localhost")
    c.cookies.set("ka_session", add_account(cfg))
    r = c.get("/api/google/callback", params={"state": "forged", "code": "x"})
    assert r.status_code == 400
    assert c.get("/api/google/status").json()["connected"] is False


def _token(tmp_path):
    (tmp_path / "google").mkdir(exist_ok=True)
    (tmp_path / "google" / "token.json").write_text(
        json.dumps(
            {
                "token": "old",
                "refresh_token": "r",
                "client_id": "id",
                "client_secret": "s",
                "token_uri": "https://oauth2.googleapis.com/token",
                "expiry": "2000-01-01T00:00:00Z",
            }
        )
    )


def test_offline_is_not_reconnect(tmp_path, monkeypatch):
    from google.auth.exceptions import TransportError
    from google.oauth2.credentials import Credentials

    _token(tmp_path)

    def offline(self, request):
        raise TransportError("no network")

    monkeypatch.setattr(Credentials, "refresh", offline)
    auth = GoogleAuth(gcfg(tmp_path), tmp_path / "google" / "token.json")
    with pytest.raises(GoogleAuthError, match="unreachable"):
        auth.credentials()
    assert auth.connected() is True


def test_token_save_is_atomic(tmp_path):
    class Creds:
        def to_json(self):
            return '{"token": "t"}'

    path = tmp_path / "google" / "token.json"
    auth = GoogleAuth(gcfg(tmp_path), path)
    auth.save(Creds())
    auth.save(Creds())
    assert [p.name for p in path.parent.iterdir()] == ["token.json"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_google_is_per_account(ctx, tmp_path, monkeypatch):
    """B's connect state, disconnect and redirect never touch A's Google sign-in."""
    from server.users import user_config

    monkeypatch.setattr(GoogleAuth, "connected", lambda self: self.token_path.is_file())
    base = ctx.config.model_copy(update={"flags": {"google": True}, "google": gcfg(tmp_path)})
    app = create_app(base, lambda: FakeAdapter([]))
    a, b = (TestClient(app, base_url="http://localhost") for _ in range(2))
    a.cookies.set("ka_session", add_account(base, "u_a"))
    b.cookies.set("ka_session", add_account(base, "u_b"))
    token = user_config(base, "u_a").google_dir / "token.json"
    token.parent.mkdir(parents=True)
    token.write_text("{}")
    assert a.get("/api/google/status").json()["connected"] is True
    assert b.get("/api/google/status").json()["connected"] is False
    b.post("/api/google/disconnect")
    assert token.is_file() and a.get("/api/google/status").json()["connected"] is True


def test_redirect_follows_the_proxy_origin(ctx, tmp_path):
    base = ctx.config.model_copy(update={"flags": {"google": True}, "google": gcfg(tmp_path)})
    app = create_app(base, lambda: FakeAdapter([]))
    app.state.trusted_proxies = {"testclient"}
    c = TestClient(app, base_url="http://localhost")
    c.cookies.set("ka_session", add_account(base))
    headers = {"x-forwarded-proto": "https", "x-forwarded-host": "ka.example.ts.net"}
    r = c.get("/api/google/login", headers=headers, follow_redirects=False)
    assert "redirect_uri=https%3A%2F%2Fka.example.ts.net%2Fapi%2Fgoogle%2Fcallback" in r.headers["location"]


def test_drive_and_sheet_come_only_from_the_account(ctx, tmp_path):
    from server.integrations.google.oauth import GoogleSetupMissing, require_drive, require_sheet
    from server.users import user_config

    base = ctx.config.model_copy(update={"google": gcfg(tmp_path)})
    ucfg = user_config(base, "u_new")
    with pytest.raises(GoogleSetupMissing, match="Your Google Drive folder is not set up yet"):
        require_drive(ucfg)
    with pytest.raises(GoogleSetupMissing, match="Your Google Sheet is not set up yet"):
        require_sheet(ucfg)


def test_account_saves_its_own_google_ids(make_client_google):
    c = make_client_google()
    r = c.put("/api/google/settings", json={"drive_folder_id": "folder-1", "sheet_id": "sheet-1"})
    assert r.status_code == 200
    assert c.get("/api/settings").json()["google"] == {"drive_folder_id": "folder-1", "sheet_id": "sheet-1"}


def test_saving_the_same_ids_again_is_fine(make_client_google, ctx):
    c = make_client_google()
    (ctx.config.repo_root / "stray-note.txt").write_text("untracked")
    ids = {"drive_folder_id": "folder-1", "sheet_id": "sheet-1"}
    assert c.put("/api/google/settings", json=ids).status_code == 200
    assert c.put("/api/google/settings", json=ids).status_code == 200
