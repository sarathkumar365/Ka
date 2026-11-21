from pathlib import Path

import pytest

from server.config import Config, ConfigError, load_config
from server.flags import FLAGS, is_on


def test_unknown_flag_in_config_is_rejected(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("data_repo: /x\nflags: {web_serch: true}\n")
    with pytest.raises(ConfigError, match="web_serch"):
        load_config(path)


def test_is_on_defaults_off_and_rejects_typos():
    cfg = Config(data_repo=Path("/x"))
    assert is_on(cfg, "loops") is False
    with pytest.raises(KeyError):
        is_on(cfg, "lops")


def test_settings_lists_every_known_flag(make_client):
    flags = make_client().get("/api/settings").json()["flag_info"]
    assert {f["name"] for f in flags} == set(FLAGS)
    assert all({"name", "description", "on"} <= f.keys() for f in flags)
