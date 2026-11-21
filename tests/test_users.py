import pytest

from server.config import Config
from server.integrations.data_repo.loader import load_data
from server.users import UserError, start_user_space, user_config
from tests.conftest import git


def _empty_repo(root):
    root.mkdir()
    (root / ".gitignore").write_text("local/\n.ka.lock\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.test")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def test_new_account_gets_valid_starter_files_in_one_commit(tmp_path):
    root = _empty_repo(tmp_path / "data")
    folder = start_user_space(Config(data_repo=root), "u_0123456789ab")
    assert folder == root / "users" / "u_0123456789ab"
    load_data(user_config(Config(data_repo=root), "u_0123456789ab").data_repo)
    assert git(root, "log", "-1", "--format=%s") == "data: start users/u_0123456789ab"
    assert git(root, "status", "--porcelain") == ""


def test_existing_folder_is_never_reused(tmp_path):
    root = _empty_repo(tmp_path / "data")
    start_user_space(Config(data_repo=root), "u_aaaaaaaaaaaa")
    with pytest.raises(UserError):
        start_user_space(Config(data_repo=root), "u_aaaaaaaaaaaa")
