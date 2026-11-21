import sqlite3
from datetime import datetime

from server.store.db import Db
from server.store.migrations import backfill_user, migrate
from tests.store.old_schema import OLD_SCHEMA

NOW = datetime(2031, 4, 5, 12, 0)


def test_migration_backfills_existing_rows(tmp_path):
    path = tmp_path / "ka.db"
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    old.execute("insert into conversations values ('C-1', '2031-01-01')")
    old.execute("insert into app_state values ('drive_seen', '[1]')")
    old.commit()
    old.close()
    db = Db.system(path)
    backfill_user(db.conn, "avery")
    assert Db(path, "avery").list_conversations()[0].id == "C-1"
    assert Db(path, "avery").get_state("drive_seen") == "[1]"
    assert Db(path, "blake").list_conversations() == []


def test_rows_are_scoped_to_their_user(tmp_path):
    a, b = Db(tmp_path / "k.db", "avery"), Db(tmp_path / "k.db", "blake")
    a.add_pending("memory", {"text": "x"}, None, NOW, "x")
    a.set_state("drive_seen", "[1]")
    cid = a.new_conversation(NOW)
    a.add_message(cid, {"role": "user", "content": "secret plan"}, NOW)
    assert b.list_pending() == [] and b.get_state("drive_seen") is None
    assert b.search("secret") == [] and len(a.search("secret")) == 1
    assert not b.conversation_exists(cid)


def test_migrate_is_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "k.db")
    assert migrate(conn) == migrate(conn)


def test_server_code_always_names_the_user():
    """A Db opened without a user writes rows as the test default user."""
    import re
    from pathlib import Path

    root = Path(__file__).parents[2] / "server"
    bad = [
        f"{p.relative_to(root)}:{n}"
        for p in root.rglob("*.py")
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if re.search(r"\bDb\((?!.*user)", line) and "class Db" not in line
    ]
    assert bad == []
