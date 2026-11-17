"""Google sign-in: installed-app OAuth with a stored refresh token. Secrets never leave local/."""

import os
import secrets
import tempfile
from pathlib import Path

from google.auth.exceptions import GoogleAuthError as _LibAuthError
from google.auth.exceptions import TransportError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

from server.config import GoogleConfig

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
# Google echoes scopes in its own order and adds openid; oauthlib would call that a change.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GoogleAuthError(Exception):
    """Safe to show: never contains tokens or secrets."""


class GoogleUnreachable(GoogleAuthError):
    """Network trouble: the sign-in is still good, so do not ask the owner to reconnect."""


class GoogleAuth:
    def __init__(self, cfg: GoogleConfig, token_path: Path) -> None:
        self.cfg, self.token_path = cfg, token_path
        self._pending: dict[str, str] = {}  # web-flow state -> PKCE code verifier

    def credentials(self) -> Credentials:
        if not self.token_path.is_file():
            raise GoogleAuthError("reconnect Google: not signed in")
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if not creds.valid:
                creds.refresh(Request())
                self.save(creds)
        except TransportError:
            raise GoogleUnreachable("Google unreachable; try again later") from None
        except (_LibAuthError, ValueError, KeyError) as e:
            raise GoogleAuthError(f"reconnect Google: {type(e).__name__}") from None
        return creds

    def connected(self) -> bool:
        try:
            self.credentials()
        except GoogleUnreachable:
            return True
        except GoogleAuthError:
            return False
        return True

    def email(self) -> str | None:
        try:
            resp = AuthorizedSession(self.credentials()).get(USERINFO, timeout=10)
        except (GoogleAuthError, OSError):
            return None
        return resp.json().get("email") if resp.ok else None

    def save(self, creds) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        # temp file then rename: a reader on another thread never sees a half-written token
        fd, tmp = tempfile.mkstemp(dir=self.token_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(creds.to_json())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.token_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def disconnect(self) -> None:
        self.token_path.unlink(missing_ok=True)

    def login_console(self) -> None:
        flow = InstalledAppFlow.from_client_secrets_file(str(self.cfg.client_file), SCOPES)
        self.save(flow.run_local_server(port=0, access_type="offline", prompt="consent"))

    def login_url(self, redirect: str) -> str:
        state = secrets.token_urlsafe(24)
        flow = Flow.from_client_secrets_file(
            str(self.cfg.client_file), SCOPES, redirect_uri=redirect, state=state
        )
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        self._pending[state] = flow.code_verifier
        return url

    def finish(self, code: str, state: str, redirect: str) -> None:
        verifier = self._pending.pop(state, None)
        if verifier is None:
            raise GoogleAuthError("sign-in expired or forged; start again")
        flow = Flow.from_client_secrets_file(
            str(self.cfg.client_file),
            SCOPES,
            redirect_uri=redirect,
            state=state,
            code_verifier=verifier,
        )
        try:
            flow.fetch_token(code=code)
        except Exception as e:  # noqa: BLE001  oauthlib raises many types; none are safe to echo
            raise GoogleAuthError(f"Google sign-in failed: {type(e).__name__}") from None
        self.save(flow.credentials)


def auth_for(cfg) -> GoogleAuth:
    if cfg.google is None:
        raise GoogleAuthError("google is not configured in config.yaml")
    return GoogleAuth(cfg.google, cfg.google_dir / "token.json")
