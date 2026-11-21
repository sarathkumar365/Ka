"""Real-model evals. Opt in with KA_LIVE_EVALS=1; costs money.

Each case runs `case.runs` times: finance cases must pass every run, others a majority. Code checks
run first; the LLM judge (models.grader, Opus) only grades cases with a rubric whose checks passed.
Results append to tests/evals/results/<date>.jsonl; `python -m tests.evals.compare` lists new
failures against the previous file. Select a set with `-m regression` or `-m capability`.
"""

import os
from datetime import date

import pytest

from server.agent.adapters import build_adapter
from server.config import load_config
from server.env import load_env
from tests.evals.cases import CASES
from tests.evals.compare import RESULTS, record
from tests.evals.harness import grade, needed, run_case
from tests.evals.judge import judge

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("KA_LIVE_EVALS") != "1", reason="set KA_LIVE_EVALS=1"),
]


def _model(cfg, task: str):
    if hasattr(cfg, "model_for"):
        return cfg.model_for(task)
    return cfg.models.get(task, cfg.models["default"])


@pytest.mark.parametrize(
    "case",
    [pytest.param(c, marks=getattr(pytest.mark, c.suite)) for c in CASES],
    ids=lambda c: f"q{c.id:02d}",
)
def test_live(case, tmp_path):
    load_env()
    cfg = load_config()
    which = "local" if os.environ.get("KA_LIVE_LOCAL") else "chat"
    adapter = build_adapter(cfg.models["local"] if which == "local" else _model(cfg, "chat"))
    grader = build_adapter(_model(cfg, "grader")) if case.rubric else None
    failures, rows = [], []
    for i in range(case.runs):
        run = run_case(case, adapter, tmp_path / f"run{i}")
        problems = grade(case, run)
        if not problems and grader is not None:
            ok, reason = judge(grader, case.question, run.answer, case.rubric)
            if not ok:
                problems.append(f"judge: {reason}")
        failures.append(problems)
        rows.append({"case": case.id, "run": i, "suite": case.suite, "passed": not problems,
                     "failures": problems, "model": which})  # fmt: skip
    record(RESULTS / f"{date.today().isoformat()}.jsonl", rows)
    passed = sum(1 for p in failures if not p)
    detail = "\n".join(f"run {i}: {p or 'ok'}" for i, p in enumerate(failures))
    assert passed >= needed(case), f"q{case.id} passed {passed}/{case.runs}\n{detail}"
