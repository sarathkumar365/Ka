"""Real-model evals. Opt in with KA_LIVE_EVALS=1; costs money. Each case runs 3 times; 2 must pass."""

import os

import pytest

from server.agent.adapters import build_adapter
from server.config import load_config
from server.env import load_env
from tests.evals.cases import CASES
from tests.evals.harness import grade, run_case

RUNS, NEED = 3, 2

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("KA_LIVE_EVALS") != "1", reason="set KA_LIVE_EVALS=1"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"q{c.id:02d}")
def test_live(case, tmp_path):
    load_env()
    cfg = load_config()
    adapter = build_adapter(cfg.models["local" if os.environ.get("KA_LIVE_LOCAL") else "default"])
    failures = []
    for i in range(RUNS):
        run = run_case(case, adapter, tmp_path / f"run{i}")
        problems = grade(case, run)
        failures.append(problems)
    passed = sum(1 for p in failures if not p)
    detail = "\n".join(f"run {i}: {p or 'ok'}" for i, p in enumerate(failures))
    assert passed >= NEED, f"q{case.id} passed {passed}/{RUNS}\n{detail}"
