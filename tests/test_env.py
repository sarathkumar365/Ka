import os

from server.env import load_env


def test_load_env_sets_missing_and_keeps_existing(tmp_path, monkeypatch):
    monkeypatch.delenv("KA_T_NEW", raising=False)
    monkeypatch.setenv("KA_T_OLD", "keep")
    f = tmp_path / ".env"
    f.write_text("# c\n\nKA_T_NEW=abc\nKA_T_OLD=override\n")
    load_env(f)
    assert os.environ["KA_T_NEW"] == "abc"
    assert os.environ["KA_T_OLD"] == "keep"
    monkeypatch.delenv("KA_T_NEW")


def test_load_env_missing_file_is_fine(tmp_path):
    load_env(tmp_path / "none")
