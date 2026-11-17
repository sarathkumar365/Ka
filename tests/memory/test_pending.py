from datetime import UTC, date, datetime

import pytest

from server.integrations.data_repo.loader import load_data
from server.memory.pending import PendingError, approve_pending, queue_memory, reject_pending
from server.store.db import Db
from tests.conftest import git

NOW = datetime(2031, 4, 5, tzinfo=UTC)
TODAY = date(2031, 4, 5)


@pytest.fixture
def setup(ctx):
    return ctx.config.data_repo, Db(":memory:")


def queue(db, repo, text, replaces=None, type="fact"):
    return queue_memory(db, load_data(repo), text, type, replaces, "C-1", NOW)


def test_queue_memory_dedupes_and_validates_replaces(setup):
    repo, db = setup
    assert queue(db, repo, "Works at a startup")["queued"] is True
    assert queue(db, repo, "  works AT a startup ")["reason"] == "duplicate"
    assert queue(db, repo, "prefers remote roles")["reason"] == "duplicate"  # active memory M-0001
    with pytest.raises(PendingError, match="M-9999"):
        queue(db, repo, "new thing", replaces="M-9999")


def test_approve_adds_memory_commit_and_marks_item(setup):
    repo, db = setup
    pid = queue(db, repo, "Has a dog named Rex")["pending_id"]
    before = git(repo, "rev-list", "--count", "HEAD")
    approve_pending(pid, repo, db, TODAY)
    entries = load_data(repo).memory.entries
    new = next(e for e in entries if e.text == "Has a dog named Rex")
    assert new.status == "active" and new.source == "C-1"
    assert git(repo, "rev-list", "--count", "HEAD") == str(int(before) + 1)
    assert db.list_pending() == [] and db.list_pending("approved")[0].id == pid


def test_approve_contradiction_adds_new_and_retires_old_with_replaced_by(setup):
    repo, db = setup
    pid = queue(db, repo, "Prefers hybrid roles", replaces="M-0001", type="preference")[
        "pending_id"
    ]
    before = git(repo, "rev-list", "--count", "HEAD")
    approve_pending(pid, repo, db, TODAY)
    by_id = {e.id: e for e in load_data(repo).memory.entries}
    new = next(e for e in by_id.values() if e.text == "Prefers hybrid roles")
    assert by_id["M-0001"].status == "retired" and by_id["M-0001"].replaced_by == new.id
    assert git(repo, "rev-list", "--count", "HEAD") == str(int(before) + 2)


def test_approve_with_dirty_memory_file_leaves_item_pending(setup):
    repo, db = setup
    pid = queue(db, repo, "Likes tea")["pending_id"]
    (repo / "memory.yaml").write_text((repo / "memory.yaml").read_text() + "# hand edit\n")
    with pytest.raises(PendingError, match="uncommitted"):
        approve_pending(pid, repo, db, TODAY)
    assert [i.id for i in db.list_pending()] == [pid]


def test_reject_marks_item_rejected(setup):
    repo, db = setup
    pid = queue(db, repo, "Likes coffee")["pending_id"]
    reject_pending(pid, db)
    assert db.list_pending() == [] and db.list_pending("rejected")[0].id == pid


def test_approve_rechecks_duplicate_and_replaces_at_approval_time(setup):
    repo, db = setup
    a = queue(db, repo, "Prefers hybrid roles", replaces="M-0001")["pending_id"]
    b = queue(db, repo, "Prefers office roles", replaces="M-0001")["pending_id"]
    c = queue(db, repo, "Likes jazz")["pending_id"]
    approve_pending(a, repo, db, TODAY)
    with pytest.raises(PendingError, match="no longer active"):
        approve_pending(b, repo, db, TODAY)
    from server.agent.tools.write_tools import remember  # noqa: F401  (registers the tool)
    from server.integrations.data_repo.writer import Patch, apply_change, plan_change

    fields = {
        "type": "fact",
        "text": "likes JAZZ",
        "created": "2031-04-05",
        "updated": "2031-04-05",
        "status": "active",
    }
    apply_change(repo, plan_change(repo, Patch(target="memory", op="add", fields=fields)))
    with pytest.raises(PendingError, match="already"):
        approve_pending(c, repo, db, TODAY)
    assert {i.id for i in db.list_pending()} == {b, c}
