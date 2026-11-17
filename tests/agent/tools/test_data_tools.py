from server.agent.tools import run_tool


def test_search_finds_record_by_id_and_text(ctx):
    hits = run_tool("search", {"query": "react"}, ctx)["hits"]
    assert ("jobs.yaml", "H-003") in [(h["file"], h["id"]) for h in hits]
    hits = run_tool("search", {"query": "CORNER"}, ctx)["hits"]
    assert ("rules/merchants.yaml", "R-001") in [(h["file"], h["id"]) for h in hits]


def test_get_jobs_hides_retired_highlights_by_default(ctx):
    def ids(result):
        return [h["id"] for j in result["jobs"] for h in j["highlights"]]

    assert "H-004" not in ids(run_tool("get_jobs", {}, ctx))
    assert "H-004" in ids(run_tool("get_jobs", {"include_retired": True}, ctx))


def test_get_jobs_gives_each_job_the_key_propose_change_needs(ctx):
    keys = [j["key"] for j in run_tool("get_jobs", {}, ctx)["jobs"]]
    assert keys == ["Acme Widgets|2022-03", "Beta Labs|2019-06"]
