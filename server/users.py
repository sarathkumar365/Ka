"""Per-user data: everything personal lives under data_repo/users/<user_id>/.

An account's view of the app is a Config whose data_repo is that account's folder and whose
repo_root is the shared data repo (database, commit lock). Every account starts empty.
"""

import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ruamel.yaml import YAML

from server.config import Config, GoogleConfig
from server.locks import repo_lock

STARTER = Path(__file__).parent / "users_starter"


class UserError(Exception):
    """Safe to show the owner."""


def user_root(cfg: Config, user_id: str) -> Path:
    return (cfg.repo_root or cfg.data_repo) / "users" / user_id


def _settings(root: Path) -> dict:
    path = root / "settings.yaml"
    return (YAML(typ="safe").load(path.read_text()) or {}) if path.is_file() else {}


def user_tz(cfg: Config) -> ZoneInfo | None:
    """The account's time zone from its profile; None means the server's own."""
    path = cfg.data_repo / "profile.yaml"
    try:
        name = (YAML(typ="safe").load(path.read_text()) or {}).get("timezone")
        return ZoneInfo(name) if name else None
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return None


def local_today(cfg: Config) -> date:
    return datetime.now(user_tz(cfg)).date()


def user_config(cfg: Config, user_id: str) -> Config:
    base = cfg.repo_root or cfg.data_repo
    root = base / "users" / user_id
    google = cfg.google
    if google is not None:
        s = _settings(root)
        google = GoogleConfig(
            client_file=google.client_file,
            drive_folder_id=s.get("drive_folder_id") or None,  # this account's only, never shared
            sheet_id=s.get("sheet_id") or None,
        )
    return cfg.model_copy(
        update={"data_repo": root, "repo_root": base, "user_id": user_id, "google": google}
    )


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["git failed"])[0]
        raise UserError(f"git {args[0]}: {first}")
    return done.stdout.strip()


def start_user_space(cfg: Config, user_id: str) -> Path:
    """A new account's folder from the starter files, committed once. Never reuses a folder."""
    base = cfg.repo_root or cfg.data_repo
    root = base / "users" / user_id
    if root.exists():
        raise UserError(f"users/{user_id} already exists")
    with repo_lock(base):
        try:
            shutil.copytree(STARTER, root)
            _git(base, "add", "--", f"users/{user_id}")
            _git(base, "commit", "-q", "-m", f"data: start users/{user_id}", "--", f"users/{user_id}")
        except BaseException:
            subprocess.run(
                ["git", "-C", str(base), "reset", "-q", "--", f"users/{user_id}"],
                capture_output=True, check=False,
            )  # fmt: skip
            shutil.rmtree(root, ignore_errors=True)
            raise
    return root


def resolve_user(db, username: str | None) -> str:
    """The account a CLI command acts for: the one named, or the only one there is."""
    if username:
        row = db.conn.execute("select id from users where username=?", (username,)).fetchone()
        if row is None:
            raise UserError(f"no account named {username}")
        return row[0]
    rows = db.conn.execute("select id from users").fetchall()
    if not rows:
        raise UserError("no accounts yet: sign up in the app")
    if len(rows) > 1:
        raise UserError("several accounts: pass --user USERNAME")
    return rows[0][0]
