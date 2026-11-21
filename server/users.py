"""Per-user data: everything personal lives under data_repo/users/<user_id>/.

A user's view of the app is a Config whose data_repo is that user's folder and whose repo_root is
the shared data repo (database, denylist). Callers that took a Config keep working unchanged.
"""

import shutil
import subprocess
from pathlib import Path

from ruamel.yaml import YAML

from server.config import Config, GoogleConfig
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import FILES

STARTER = Path(__file__).parent / "users_starter"
LOCAL_DIRS = ("finance", "statements", "google", "intake")
TOOLKIT_MEMORY = ("finance", "movies")


class UserError(Exception):
    """Safe to show the owner."""


def user_root(cfg: Config, user_id: str) -> Path:
    return (cfg.repo_root or cfg.data_repo) / "users" / user_id


def _settings(root: Path) -> dict:
    path = root / "settings.yaml"
    return (YAML(typ="safe").load(path.read_text()) or {}) if path.is_file() else {}


def user_config(cfg: Config, user_id: str) -> Config:
    base = cfg.repo_root or cfg.data_repo
    root = base / "users" / user_id
    google = cfg.google
    if google is not None:
        s = _settings(root)
        google = GoogleConfig(
            client_file=google.client_file,
            drive_folder_id=s.get("drive_folder_id") or google.drive_folder_id,
            sheet_id=s.get("sheet_id") or google.sheet_id,
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


def _legacy_files(base: Path) -> list[str]:
    names = [name for name, _ in FILES.values() if name != "memory/core.yaml"] + ["memory.yaml"]
    return [n for n in names if (base / n).is_file()]


def claim_legacy_data(cfg: Config, user_id: str) -> list[str]:
    """Move the old root layout into users/<user_id>/ with one commit. Returns the moved files.

    All or nothing: if any step fails before the commit, the repo is reset to how it was.
    """
    base = cfg.repo_root or cfg.data_repo
    root = base / "users" / user_id
    if _git(base, "status", "--porcelain", "--untracked-files=no"):
        raise UserError("the data repo has uncommitted changes; commit or discard them first")
    if root.exists() and any(root.iterdir()):
        raise UserError(f"users/{user_id} already exists")
    moved = _legacy_files(base)
    tracked = set(_git(base, "ls-files", "--", *moved).splitlines()) if moved else set()
    loose = [n for n in moved if n not in tracked]
    if loose:
        raise UserError(f"commit these files in the data repo first: {', '.join(loose)}")
    try:
        _move_and_commit(cfg, base, root, user_id, moved)
    except BaseException:
        _git(base, "reset", "-q", "--hard", "HEAD")  # the repo was clean, so this only undoes us
        shutil.rmtree(root, ignore_errors=True)
        raise
    local = root / "local"
    for name in LOCAL_DIRS:
        src = base / "local" / name
        if src.is_dir():
            local.mkdir(exist_ok=True)
            shutil.move(str(src), str(local / name))
    finance = local / "finance"
    if finance.is_dir():
        _stamp_finance(finance, user_id)
    return moved


def _move_and_commit(cfg: Config, base: Path, root: Path, user_id: str, moved: list[str]) -> None:
    (root / "memory").mkdir(parents=True, exist_ok=True)
    (root / "rules").mkdir(exist_ok=True)
    for name in moved:
        dest = "memory/core.yaml" if name == "memory.yaml" else name
        _git(base, "mv", "--", name, f"users/{user_id}/{dest}")
    # A legacy repo keeps its own files and only gains the toolkit memory files; a new user
    # starts from empty valid files.
    for rel in sorted(p.relative_to(STARTER) for p in STARTER.rglob("*.yaml")):
        target = root / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(STARTER / rel, target)
    if cfg.google is not None and (cfg.google.drive_folder_id or cfg.google.sheet_id):
        settings = {"drive_folder_id": cfg.google.drive_folder_id, "sheet_id": cfg.google.sheet_id}
        YAML().dump({k: v for k, v in settings.items() if v}, root / "settings.yaml")
    _git(base, "add", "--", f"users/{user_id}")
    message = f"data: move personal files under users/{user_id}" if moved else (
        f"data: start users/{user_id}"
    )
    _git(base, "commit", "-q", "-m", message)


def _stamp_finance(folder: Path, user_id: str) -> None:
    store = CsvFinanceStore(folder)
    with store._locked():
        rows = [t.model_copy(update={"user_id": user_id}) for t in store.transactions()]
        stmts = [s.model_copy(update={"user_id": user_id}) for s in store.statements()]
        from server.finance.models import StatementRecord, Transaction

        if rows:
            store._write(store._transactions, Transaction, rows)
        if stmts:
            store._write(store._statements, StatementRecord, stmts)


def only_user(db) -> str:
    """The single account, for CLI commands and background jobs."""
    rows = db.conn.execute("select id from users order by created_at").fetchall()
    if not rows:
        raise UserError("no account yet: run ka serve and create it in onboarding")
    if len(rows) > 1:
        raise UserError("several accounts: pass --user")
    return rows[0][0]
