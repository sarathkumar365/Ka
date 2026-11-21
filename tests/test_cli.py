import argparse
from datetime import datetime

from server import cli
from server.store.db import Db
from tests.conftest import add_account


def test_statement_cards_are_listed_but_decided_in_the_app(ctx, monkeypatch, capsys):
    cfg = ctx.config
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli, "_USER", cfg.user_id)
    add_account(cfg)
    db = Db(cfg.db_path, cfg.user_id)
    card = db.add_pending("statement", {"file": "oct.pdf", "account": "A-01", "rows": 12}, "drive", datetime.now())
    assert cli._pending(argparse.Namespace(action=None)) == 0
    assert "oct.pdf" in capsys.readouterr().out
    assert cli._pending(argparse.Namespace(action="reject", id=card)) == 1  # decided in the app only
    assert db.get_pending(card).status == "pending"


def test_check_on_a_fresh_install_says_sign_up(tmp_path, monkeypatch, capsys):
    from server.config import Config

    monkeypatch.setattr(cli, "load_config", lambda: Config(data_repo=tmp_path))
    monkeypatch.setattr(cli, "_USER", None)
    assert cli._check(argparse.Namespace()) == 0
    assert "sign up in the app" in capsys.readouterr().out


def test_check_validates_every_account(ctx, monkeypatch, capsys):
    import shutil

    from server.config import Config

    root = ctx.config.data_repo.parents[1]  # the account config points at users/avery
    base = Config(data_repo=root)
    add_account(base, "avery")
    shutil.copytree(root / "users" / "avery", root / "users" / "blake")
    (root / "users" / "blake" / "accounts.yaml").write_text("accounts: [not, valid: {")
    add_account(base, "blake")
    monkeypatch.setattr(cli, "load_config", lambda: base)
    monkeypatch.setattr(cli, "_USER", None)
    assert cli._check(argparse.Namespace()) == 1
    out = capsys.readouterr().out
    assert "ok: avery" in out and "blake" in out
