from pathlib import Path

import pytest

from server.config import ConfigError, load_config


def test_loads_paths_flags_and_expands_home(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("data_repo: ~/x\nflags:\n  loops: false\n")
    cfg = load_config(f)
    assert cfg.data_repo == Path.home() / "x"
    assert cfg.flags["loops"] is False
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


def test_models_parse_and_unknown_provider_is_rejected(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(
        "data_repo: /x\nmodels:\n  default: {provider: openrouter, model: m1}\n"
        "  local: {provider: ollama, model: g, base_url: 'http://localhost:11434/v1'}\n"
    )
    cfg = load_config(f)
    assert cfg.models["default"].model == "m1"
    assert cfg.models["local"].base_url == "http://localhost:11434/v1"
    assert cfg.db_path == Path("/x/local/ka.db")
    f.write_text("data_repo: /x\nmodels:\n  default: {provider: bogus, model: m}\n")
    with pytest.raises(ConfigError):
        load_config(f)


def test_per_account_values_never_come_from_config(tmp_path):
    import pytest

    from server.config import ConfigError, load_config

    path = tmp_path / "config.yaml"
    path.write_text(f"data_repo: {tmp_path}\nuser_id: avery\n")
    with pytest.raises(ConfigError, match="not allowed in config.yaml: user_id"):
        load_config(path)
    client = tmp_path / "client.json"
    client.write_text("{}")
    path.write_text(f"data_repo: {tmp_path}\ngoogle:\n  client_file: {client}\n  sheet_id: S\n")
    assert load_config(path).google.sheet_id is None
