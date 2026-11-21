import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from server.agent.tools.registry import ToolContext
from server.config import Config
from server.finance.store import CsvFinanceStore
from server.users import user_config

FIXTURE = Path(__file__).parent / "fixtures" / "data"
USER = "avery"


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def make_repo(root: Path, user: str = USER) -> Config:
    """A data repo with the fixture as one user's folder; returns that user's Config."""
    shutil.copytree(FIXTURE, root / "users" / user)
    (root / ".gitignore").write_text("local/\n.ka.lock\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.test")
    git(root, "config", "user.name", "Test")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return user_config(Config(data_repo=root), user)


def add_account(cfg: Config, user: str = USER) -> str:
    """Create the account row and a session; returns the session token."""
    from server.auth.sessions import new_session
    from server.store.db import Db

    db = Db.system(cfg.db_path)
    now = datetime.now()
    if not db.conn.execute("select 1 from users where id=?", (user,)).fetchone():
        with db.conn:
            db.conn.execute(
                "insert into users (id, username, password_hash, created_at) values (?,?,?,?)",
                (user, user, "x", now.isoformat()),
            )
    token = new_session(db, user, now, "test")
    db.conn.close()
    return token


@pytest.fixture
def ctx(tmp_path) -> ToolContext:
    cfg = make_repo(tmp_path / "repo")
    return ToolContext(config=cfg, store=CsvFinanceStore(tmp_path / "fin"))
