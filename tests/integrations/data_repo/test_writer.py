import pytest

from server.integrations.data_repo.loader import load_data
from server.integrations.data_repo.writer import (
    ChangeError,
    Patch,
    apply_change,
    dump_text,
    load_text,
    plan_change,
)
from tests.conftest import FIXTURE, git

JOB = "Acme Widgets|2022-03"


@pytest.fixture
def repo(ctx):
    return ctx.config.data_repo


def test_noop_roundtrip_is_byte_identical():
    for path in FIXTURE.rglob("*.yaml"):
        text = path.read_text()
        assert dump_text(load_text(text)) == text, path.name


def test_add_highlight_assigns_next_id_validates_and_commits(repo):
    patch = Patch(
        target="highlight", op="add", parent=JOB, fields={"text": "Shipped X", "domains": ["D-01"]}
    )
    plan = plan_change(repo, patch)
    assert "H-005" in plan.diff and set(plan.files) == {"jobs.yaml", "ids.yaml"}
    before = git(repo, "rev-list", "--count", "HEAD")
    sha = apply_change(repo, plan)
    assert git(repo, "rev-list", "--count", "HEAD") == str(int(before) + 1)
    assert git(repo, "status", "--porcelain", "--", "jobs.yaml", "ids.yaml") == ""
    assert git(repo, "rev-parse", "--short", "HEAD") == sha
    data = load_data(repo)
    assert "H-005" in [h.id for j in data.jobs.jobs for h in j.highlights]
    assert data.ids.next["H"] == 6


def test_invalid_patch_changes_nothing(repo):
    before = (git(repo, "rev-list", "--count", "HEAD"), (repo / "jobs.yaml").read_text())
    bad = Patch(target="highlight", op="add", parent=JOB, fields={"text": "x", "domains": ["D-99"]})
    with pytest.raises(ChangeError, match="D-99"):
        plan_change(repo, bad)
    assert (git(repo, "rev-list", "--count", "HEAD"), (repo / "jobs.yaml").read_text()) == before


def test_stale_plan_and_dirty_file_are_refused(repo):
    def relabel(label):
        return plan_change(
            repo, Patch(target="account", op="update", key="A-01", fields={"label": label})
        )

    first, second = relabel("One"), relabel("Two")
    apply_change(repo, first)
    with pytest.raises(ChangeError, match="changed since proposal"):
        apply_change(repo, second)
    (repo / "guardrails.yaml").write_text((repo / "guardrails.yaml").read_text() + "# hand edit\n")
    with pytest.raises(ChangeError, match="uncommitted"):
        plan_change(repo, Patch(target="guardrail", op="delete", key="G-02"))


def test_job_edits_cannot_carry_highlights_or_reuse_ids(repo):
    smuggle = {"highlights": [{"id": "H-003", "text": "new"}]}
    for op, extra in (("update", {"key": JOB}), ("add", {})):
        fields = {
            **smuggle,
            "company": "New Co",
            "start": "2030-01",
            "position": "x",
            "employment_type": "contract",
        }
        with pytest.raises(ChangeError, match="highlight"):
            plan_change(repo, Patch(target="job", op=op, fields=fields, **extra))


def test_first_record_in_an_empty_section_gets_an_id(repo):
    (repo / "other.yaml").write_text("types: [project]\n")
    git(repo, "commit", "-q", "-am", "empty other")
    plan = plan_change(
        repo, Patch(target="other_record", op="add", fields={"type": "project", "name": "Ka"})
    )
    assert plan.key == "O-001" and "name: Ka" in plan.files["other.yaml"][1]


def test_apply_rolls_back_on_any_failure_not_only_git_errors(repo, monkeypatch):
    from server.integrations.data_repo import writer

    before = (repo / "accounts.yaml").read_text()
    plan = plan_change(
        repo, Patch(target="account", op="update", key="A-01", fields={"label": "Changed"})
    )

    real = writer._git

    def boom(root, *args):
        if args[0] == "add":
            raise OSError("disk full")
        return real(root, *args)

    monkeypatch.setattr(writer, "_git", boom)
    with pytest.raises(OSError):
        apply_change(repo, plan)
    assert (repo / "accounts.yaml").read_text() == before


def test_apply_revalidates_whole_repo_after_a_hand_edit_elsewhere(repo):
    plan = plan_change(
        repo,
        Patch(
            target="merchant_rule",
            op="add",
            fields={"match": "Book Store", "category": "dining", "approved": "2026-02-01"},
        ),
    )
    cats = repo / "categories.yaml"
    cats.write_text(cats.read_text().replace("dining, ", ""))
    git(repo, "commit", "-q", "-am", "drop dining")
    before = (repo / "rules/merchants.yaml").read_text()
    with pytest.raises(ChangeError, match="dining"):
        apply_change(repo, plan)
    assert (repo / "rules/merchants.yaml").read_text() == before
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
