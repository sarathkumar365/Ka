import shutil
import subprocess
from pathlib import Path

import pytest

from server.agent.tools.registry import ToolContext
from server.config import Config
from server.finance.store import CsvFinanceStore

FIXTURE = Path(__file__).parent / "fixtures" / "data"


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def ctx(tmp_path) -> ToolContext:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return ToolContext(config=Config(data_repo=repo), store=CsvFinanceStore(tmp_path / "fin"))
