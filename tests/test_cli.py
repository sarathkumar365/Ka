import argparse
from datetime import datetime

from server import cli
from server.store.db import Db


def test_statement_cards_are_listed_but_decided_in_the_app(ctx, monkeypatch, capsys):
    cfg = ctx.config
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    db = Db(cfg.db_path)
    card = db.add_pending("statement", {"file": "oct.pdf", "account": "A-01", "rows": 12}, "drive", datetime.now())
    assert cli._pending(argparse.Namespace(action=None)) == 0
    assert "oct.pdf" in capsys.readouterr().out
    assert cli._pending(argparse.Namespace(action="reject", id=card)) == 1  # decided in the app only
    assert db.get_pending(card).status == "pending"
