import pytest

from server.agent.tools import ToolError, run_tool
from server.toolkits.base import available


def test_movies_hidden_when_flag_off(ctx):
    assert "movies" not in {m.name for m in available(ctx.config)}
    on = ctx.config.model_copy(update={"flags": {"movies": True}})
    assert "movies" in {m.name for m in available(on)}


def test_missing_token_is_a_clear_error(ctx, monkeypatch):
    monkeypatch.delenv("TMDB_API_TOKEN", raising=False)
    with pytest.raises(ToolError, match="TMDB_API_TOKEN"):
        run_tool("movies_search", {"query": "dune"}, ctx)
