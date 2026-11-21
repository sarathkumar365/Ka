from datetime import date

import pytest

from server.intake.approve import approve_bundle, reject_bundle
from server.intake.queue import queue_draft
from server.integrations.data_repo.loader import load_data
from server.memory.pending import PendingError
from server.store.db import Db
from tests.conftest import git
from tests.intake.test_queue import NOW, draft

TODAY = date(2031, 4, 6)


@pytest.fixture
def queued(ctx):
    db = Db(":memory:", "avery")
    queue_draft(db, load_data(ctx.config.data_repo), draft(), "r.pdf", NOW)
    cards = {(c.payload["section"], c.payload["title"]): c for c in db.list_pending()}
    return ctx.config.data_repo, db, cards


def commits(repo):
    return int(git(repo, "rev-list", "--count", "HEAD"))


def test_job_card_applies_as_one_commit_with_ids_and_resolved_tags(queued):
    repo, db, cards = queued
    approve_bundle(cards[("domains", "Domains")].id, None, repo, db, TODAY)
    before = commits(repo)
    job = cards[("job", "Globex Corp, Engineer")]
    approve_bundle(job.id, None, repo, db, TODAY)
    assert commits(repo) == before + 1
    saved = next(j for j in load_data(repo).jobs.jobs if j.company == "Globex Corp")
    assert [h.id for h in saved.highlights] == ["H-005", "H-006"]
    robotics = next(d.id for d in load_data(repo).jobs.domains if d.name == "Robotics")
    assert saved.highlights[0].domains == [robotics]


def test_unticked_highlight_is_not_written(queued):
    repo, db, cards = queued
    approve_bundle(cards[("domains", "Domains")].id, None, repo, db, TODAY)
    job = cards[("job", "Globex Corp, Engineer")]
    approve_bundle(job.id, ["i1", "i3"], repo, db, TODAY)
    saved = next(j for j in load_data(repo).jobs.jobs if j.company == "Globex Corp")
    assert [h.text for h in saved.highlights] == ["Cut latency"]


def test_job_card_refused_until_domains_card_is_decided(queued):
    repo, db, cards = queued
    job = cards[("job", "Globex Corp, Engineer")]
    with pytest.raises(PendingError, match="Domains"):
        approve_bundle(job.id, None, repo, db, TODAY)
    reject_bundle(cards[("domains", "Domains")].id, db)
    approve_bundle(job.id, None, repo, db, TODAY)
    saved = next(j for j in load_data(repo).jobs.jobs if j.company == "Globex Corp")
    assert saved.highlights[0].domains == []  # rejected domain: its tag is dropped


def test_approving_twice_is_refused_and_writes_once(queued):
    repo, db, cards = queued
    card = cards[("education", "Education")]
    approve_bundle(card.id, None, repo, db, TODAY)
    n = commits(repo)
    with pytest.raises(PendingError):
        approve_bundle(card.id, None, repo, db, TODAY)
    assert commits(repo) == n


def test_blocked_card_and_bad_selection_are_refused(ctx):
    db = Db(":memory:", "avery")
    d = draft(profile={}, education=[], domains=[], jobs=[{"company": "NoDate", "position": "x"}])
    queue_draft(db, load_data(ctx.config.data_repo), d, "r", NOW)
    [card] = db.list_pending()
    with pytest.raises(PendingError, match="start date"):
        approve_bundle(card.id, None, ctx.config.data_repo, db, TODAY)
    with pytest.raises(PendingError):
        approve_bundle(card.id, ["nope"], ctx.config.data_repo, db, TODAY)
