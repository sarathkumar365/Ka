from pathlib import Path

import pytest

from server.config import ConfigError, load_config


def test_loads_paths_flags_and_expands_home(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("data_repo: ~/x\nflags:\n  voice_mic: false\n")
    cfg = load_config(f)
    assert cfg.data_repo == Path.home() / "x"
    assert cfg.flags["voice_mic"] is False
    assert cfg.finance_dir == Path.home() / "x" / "local" / "finance"


def test_missing_file_and_unknown_key_raise(tmp_path):
    with pytest.raises(ConfigError, match="config.example.yaml"):
        load_config(tmp_path / "nope.yaml")
    f = tmp_path / "c.yaml"
    f.write_text("data_repo: /x\nbogus: 1\n")
    with pytest.raises(ConfigError):
        load_config(f)
    f.write_text("data_repo: [\n")
    with pytest.raises(ConfigError, match="c.yaml"):
        load_config(f)
