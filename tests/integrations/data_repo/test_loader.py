import shutil
from pathlib import Path

import pytest

from server.cli import main
from server.integrations.data_repo.loader import DataRepoError, load_data

FIX = Path(__file__).parents[2] / "fixtures" / "data"


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(FIX, tmp_path / "d")
    return tmp_path / "d"


def test_loads_fixture_repo():
    data = load_data(FIX)
    assert data.profile.name == "Avery Quinn"
    assert len(data.accounts.accounts) == 3


def test_errors_name_file_and_field(repo):
    (repo / "accounts.yaml").write_text("accounts:\n  - {id: A-01, kind: cash, label: x}\n")
    with pytest.raises(DataRepoError) as e:
        load_data(repo)
    assert e.value.file == "accounts.yaml" and "kind" in e.value.field


def test_broken_yaml_is_a_data_repo_error(repo):
    (repo / "accounts.yaml").write_text("accounts: [\n")
    with pytest.raises(DataRepoError) as e:
        load_data(repo)
    assert e.value.file == "accounts.yaml"


def test_cross_file_check_catches_unknown_domain(repo):
    p = repo / "jobs.yaml"
    p.write_text(p.read_text().replace("domains: [D-02]", "domains: [D-09]", 1))
    with pytest.raises(DataRepoError, match="D-09"):
        load_data(repo)


def test_cli_check(repo, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_repo: {repo}\n")
    monkeypatch.setenv("KA_CONFIG", str(cfg))
    assert main(["check"]) == 0
    assert "ok: 11 files" in capsys.readouterr().out
    (repo / "ids.yaml").write_text("next: {H: 1}\n")
    assert main(["check"]) == 1
    assert "ids.yaml" in capsys.readouterr().out
