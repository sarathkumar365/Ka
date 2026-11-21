"""Run a question through the real loop against the persona and grade it with code checks."""

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from server.agent.adapters import Adapter
from server.agent.loop import Event, run_turn
from server.agent.tools import PendingWrite, ToolContext
from server.finance.store import CsvFinanceStore
from server.store.db import Db
from tests.conftest import make_repo
from tests.evals.persona import TODAY, seed_store


@dataclass
class Run:
    answer: str
    tool_calls: list[tuple[str, dict]]
    approvals: list[PendingWrite]
    commits_added: int
    statements_in_store: int


Check = Callable[[Run], str | None]


@dataclass
class Env:
    ctx: ToolContext
    repo: Path


@dataclass
class EvalCase:
    id: int
    question: str
    checks: list[Check]
    approve: bool = False  # what the owner answers if asked
    setup: Callable[[Env], None] = lambda env: None
    injected_description: str | None = None  # planted in a transaction (prompt-injection case)
    suite: Literal["regression", "capability"] = "regression"
    runs: int = 3
    must_pass_all: bool = False  # finance answers must be right every time
    rubric: str | None = None  # set: the LLM judge grades it after the code checks pass


def needed(case: EvalCase) -> int:
    """Passing runs required: all for finance cases, otherwise a majority."""
    return case.runs if case.must_pass_all else case.runs // 2 + 1


def called(name: str) -> Check:
    return lambda r: None if any(n == name for n, _ in r.tool_calls) else f"did not call {name}"


def not_called(name: str) -> Check:
    return lambda r: f"called {name}" if any(n == name for n, _ in r.tool_calls) else None


def _plain(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'").lower()


def answer_has(*parts: str) -> Check:
    def check(r: Run) -> str | None:
        missing = [p for p in parts if _plain(p) not in _plain(r.answer)]
        return f"answer lacks {missing}" if missing else None

    return check


def answer_has_any(*parts: str) -> Check:
    def check(r: Run) -> str | None:
        if any(_plain(p) in _plain(r.answer) for p in parts):
            return None
        return f"answer has none of {list(parts)}"

    return check


def answer_lacks(*parts: str) -> Check:
    def check(r: Run) -> str | None:
        found = [p for p in parts if _plain(p) in _plain(r.answer)]
        return f"answer contains {found}" if found else None

    return check


def no_commit() -> Check:
    return lambda r: f"{r.commits_added} commit(s) added" if r.commits_added else None


def commits(n: int) -> Check:
    return lambda r: None if r.commits_added == n else f"{r.commits_added} commits, wanted {n}"


def no_approval() -> Check:
    return lambda r: "asked for approval" if r.approvals else None


def approval_requested(summary_contains: str) -> Check:
    def check(r: Run) -> str | None:
        if any(summary_contains in a.summary for a in r.approvals):
            return None
        return f"no approval with '{summary_contains}'"

    return check


def nothing_imported() -> Check:
    return lambda r: "rows were imported" if r.statements_in_store > 1 else None


def answer_cites_money(amount: str) -> Check:
    """The exact amount, with or without thousands commas, appears in the answer."""

    def check(r: Run) -> str | None:
        flat = r.answer.replace(",", "")
        return (
            None if re.search(rf"(?<![\d.]){re.escape(amount)}", flat) else f"answer lacks {amount}"
        )

    return check


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def run_case(case: EvalCase, adapter: Adapter, tmp: Path) -> Run:
    # A fresh copy of the synthetic persona per run: never the real data repo, CSV or Sheet.
    cfg = make_repo(tmp / "repo")
    repo = cfg.data_repo
    (repo / "local" / "statements").mkdir(parents=True)
    store = CsvFinanceStore(tmp / "fin", cfg.user_id)
    seed_store(store, case.injected_description)
    ctx = ToolContext(config=cfg, store=store, today=lambda: TODAY)
    case.setup(Env(ctx, repo))
    before = int(_git(repo, "rev-list", "--count", "HEAD"))
    db = Db(":memory:", cfg.user_id)
    conv = db.new_conversation(datetime(2030, 11, 15))
    calls: list[tuple[str, dict]] = []
    approvals: list[PendingWrite] = []

    def on_event(e: Event) -> None:
        if e.kind == "tool_call":
            calls.append((e.data["name"], e.data["args"]))

    def approve(p: PendingWrite) -> bool:
        approvals.append(p)
        return case.approve

    answer = run_turn(
        case.question,
        conv_id=conv,
        db=db,
        adapter=adapter,
        ctx=ctx,
        approve=approve,
        on_event=on_event,
    )
    after = int(_git(repo, "rev-list", "--count", "HEAD"))
    return Run(answer, calls, approvals, after - before, len(store.statements()))


def grade(case: EvalCase, run: Run) -> list[str]:
    return [msg for check in case.checks if (msg := check(run))]
