import json

from server.agent.adapters import FakeAdapter, Reply, ToolCall
from tests.evals.cases import CASES
from tests.evals.harness import Run, answer_has, called, grade, no_commit, run_case


def scripted(*calls, final):
    replies = [
        Reply(tool_calls=[ToolCall(f"c{i}", n, json.dumps(a))]) for i, (n, a) in enumerate(calls)
    ]
    return FakeAdapter([*replies, Reply(text=final)])


def case(n):
    return next(c for c in CASES if c.id == n)


def test_checks_flag_missing_tool_call_wrong_text_and_extra_commit():
    run = Run("hello", [("get_profile", {})], [], 1, 1)
    assert called("finance_summary")(run) == "did not call finance_summary"
    assert answer_has("bye")(run).startswith("answer lacks")
    assert no_commit()(run) == "1 commit(s) added"


def test_all_twenty_cases_exist_with_unique_ids():
    assert sorted(c.id for c in CASES) == list(range(1, 21))


def test_good_script_for_remember_case_passes_through_the_real_loop(tmp_path):
    c = case(12)
    adapter = scripted(
        ("remember", {"text": "likes window seats", "type": "preference"}), final="Saved."
    )
    run = run_case(c, adapter, tmp_path)
    assert grade(c, run) == []


def test_good_script_for_summary_case_passes(tmp_path):
    c = case(1)
    adapter = scripted(
        ("load_toolkit", {"name": "finance"}),
        ("finance_summary", {"start": "2030-10-01", "end": "2030-10-31"}),
        final="You spent 153.50 in October.",
    )
    assert grade(c, run_case(c, adapter, tmp_path)) == []


def test_bad_script_is_graded_as_failure(tmp_path):
    c = case(1)
    run = run_case(c, scripted(final="About 200 dollars."), tmp_path)
    assert grade(c, run)  # no tool call and wrong number


def test_answer_checks_ignore_curly_quotes():
    run = Run("I don’t have that", [], [], 0, 1)
    assert answer_has("don't have")(run) is None


def test_judge_reads_first_line():
    from tests.evals.judge import judge

    assert judge(FakeAdapter([Reply(text="PASS\nclear")]), "q", "a", "r") == (True, "clear")
    assert judge(FakeAdapter([Reply(text="fail: vague")]), "q", "a", "r")[0] is False
    assert judge(FakeAdapter([Reply(text="maybe")]), "q", "a", "r")[0] is False


def test_finance_case_needs_every_run():
    from tests.evals.harness import EvalCase, needed

    assert needed(EvalCase(1, "q", [], must_pass_all=True, runs=3)) == 3
    assert needed(EvalCase(2, "q", [])) == 2
    assert case(1).must_pass_all and not case(6).must_pass_all
    assert {c.suite for c in CASES} == {"regression"}


def test_compare_lists_regressions(tmp_path):
    from tests.evals.compare import compare, record

    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    record(a, [{"case": 1, "passed": True}, {"case": 2, "passed": False}])
    record(b, [{"case": 1, "passed": False}, {"case": 2, "passed": True}])
    assert compare(a, b) == ["q01"]


def test_run_case_uses_only_temp_copies(tmp_path):
    from tests.evals.harness import EvalCase

    seen = {}
    c = EvalCase(99, "q", [], setup=lambda env: seen.update(root=env.ctx.config.data_repo, fin=env.ctx.store.folder))
    run_case(c, FakeAdapter([Reply(text="ok")]), tmp_path)
    assert seen["root"].is_relative_to(tmp_path) and seen["fin"].is_relative_to(tmp_path)
    assert seen["root"].parent.name == "users"
