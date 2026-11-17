import json
import stat

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.config import GoogleConfig
from server.integrations.google.oauth import GoogleAuth, GoogleAuthError


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
    return GoogleConfig(client_file=client, drive_folder_id="F", sheet_id="S")


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


def test_callback_rejects_wrong_state(ctx, tmp_path):
    cfg = ctx.config.model_copy(update={"flags": {"google": True}, "google": gcfg(tmp_path)})
    c = TestClient(create_app(cfg, lambda: FakeAdapter([])), base_url="http://localhost")
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
