import shutil

import pytest

from server.config import Config
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import load_data
from server.users import UserError, claim_legacy_data, user_config
from tests.conftest import FIXTURE, git

ROW = (
    "id,account,statement_id,date,type,description,amount,balance,tag,category,linked_id\n"
    "S1-001,A-01,S1,2031-01-02,Point of sale purchase,Cafe,-4.50,95.50,purchase,,\n"
)


def _repo(root):
    root.mkdir(exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.test")
    git(root, "config", "user.name", "T")
    return root


@pytest.fixture
def legacy_repo(tmp_path):
    root = tmp_path / "data"
    shutil.copytree(FIXTURE, root)
    (root / "memory" / "core.yaml").rename(root / "memory.yaml")
    shutil.rmtree(root / "memory")
    (root / ".gitignore").write_text("local/\n.ka.lock\n")
    _repo(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    (root / "local" / "finance").mkdir(parents=True)
    (root / "local" / "finance" / "transactions.csv").write_text(ROW)
    return root


def test_claim_moves_root_layout_and_commits_once(legacy_repo):
    cfg = Config(data_repo=legacy_repo)
    before = int(git(legacy_repo, "rev-list", "--count", "HEAD"))
    moved = claim_legacy_data(cfg, "avery")
    space = user_config(cfg, "avery")
    assert "profile.yaml" in moved and (space.data_repo / "memory" / "core.yaml").is_file()
    assert (space.data_repo / "memory" / "finance.yaml").is_file()
    assert (space.finance_dir / "transactions.csv").is_file()
    assert not (legacy_repo / "profile.yaml").exists()
    assert int(git(legacy_repo, "rev-list", "--count", "HEAD")) == before + 1
    assert git(legacy_repo, "status", "--porcelain") == ""
    assert load_data(space.data_repo).profile.name == "Avery Quinn"
    rows = CsvFinanceStore(space.finance_dir).transactions()
    assert [t.user_id for t in rows] == ["avery"]
    assert space.db_path == legacy_repo / "local" / "ka.db"


def test_claim_refuses_dirty_repo(legacy_repo):
    (legacy_repo / "profile.yaml").write_text("name: edited\n")
    with pytest.raises(UserError, match="uncommitted"):
        claim_legacy_data(Config(data_repo=legacy_repo), "avery")


def test_claim_with_nothing_to_move_creates_empty_user(tmp_path):
    root = _repo(tmp_path / "data")
    git(root, "commit", "-q", "--allow-empty", "-m", "init")
    cfg = Config(data_repo=root)
    assert claim_legacy_data(cfg, "avery") == []
    assert load_data(user_config(cfg, "avery").data_repo).profile.name == ""
    assert git(root, "status", "--porcelain") == ""


def test_google_ids_move_to_user_settings(legacy_repo, tmp_path):
    g = {"client_file": tmp_path / "c.json", "drive_folder_id": "F", "sheet_id": "S"}
    cfg = Config(data_repo=legacy_repo, google=g)
    claim_legacy_data(cfg, "avery")
    bare = Config(data_repo=legacy_repo, google={"client_file": tmp_path / "c.json"})
    assert user_config(bare, "avery").google.sheet_id == "S"


def test_claim_refuses_untracked_personal_file(legacy_repo):
    (legacy_repo / "profile.yaml").unlink()
    git(legacy_repo, "commit", "-qam", "drop profile")
    (legacy_repo / "profile.yaml").write_text('name: "Untracked"\n')
    with pytest.raises(UserError, match="profile.yaml"):
        claim_legacy_data(Config(data_repo=legacy_repo), "avery")
    assert not (legacy_repo / "users").exists()


def test_failed_commit_rolls_everything_back(legacy_repo, monkeypatch):
    from server import users

    real = users._git

    def failing(root, *args):
        if args[0] == "commit":
            raise UserError("git commit: no identity")
        return real(root, *args)

    monkeypatch.setattr(users, "_git", failing)
    with pytest.raises(UserError, match="identity"):
        claim_legacy_data(Config(data_repo=legacy_repo), "avery")
    assert (legacy_repo / "profile.yaml").is_file() and not (legacy_repo / "users").exists()
    assert git(legacy_repo, "status", "--porcelain") == ""
    assert (legacy_repo / "local" / "finance" / "transactions.csv").is_file()
    monkeypatch.setattr(users, "_git", real)
    assert "profile.yaml" in claim_legacy_data(Config(data_repo=legacy_repo), "avery")  # retry works
