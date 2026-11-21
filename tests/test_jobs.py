import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from server.config import Config
from server.jobs import for_each_account
from server.users import local_today, user_config
from tests.conftest import FIXTURE, add_account, make_repo


@pytest.fixture
def two_account_cfg(tmp_path):
    cfg = make_repo(tmp_path / "repo", "u_a")
    base = Config(data_repo=cfg.repo_root)
    shutil.copytree(FIXTURE, cfg.repo_root / "users" / "u_b")
    for user in ("u_a", "u_b"):
        add_account(base, user)
    return base


def test_job_runs_for_every_account_even_if_one_fails(two_account_cfg):
    seen = []

    def job(ucfg):
        seen.append(ucfg.user_id)
        if ucfg.user_id == "u_a":
            raise RuntimeError("boom")

    for_each_account(two_account_cfg, job, "test")()
    assert seen == ["u_a", "u_b"]


def test_today_uses_the_accounts_time_zone(tmp_path):
    cfg = make_repo(tmp_path / "repo")
    profile = cfg.data_repo / "profile.yaml"
    profile.write_text(profile.read_text().replace("timezone: America/Toronto", "timezone: Pacific/Kiritimati"))
    assert "Pacific/Kiritimati" in profile.read_text()
    assert local_today(cfg) == datetime.now(ZoneInfo("Pacific/Kiritimati")).date()


def test_cli_needs_user_when_several(two_account_cfg, monkeypatch, capsys):
    from server import cli

    monkeypatch.setattr(cli, "load_config", lambda: two_account_cfg)
    assert cli.main(["pending"]) == 1
    assert "pass --user USERNAME" in capsys.readouterr().out
    assert cli.main(["--user", "nobody", "pending"]) == 1
    assert "no account named nobody" in capsys.readouterr().out
    assert cli.main(["--user", "u_b", "pending"]) == 0
    assert user_config(two_account_cfg, "u_b").user_id == "u_b"
