"""Movies toolkit: search TMDB, find recent releases, check where a film can be watched in Canada."""

import os
from datetime import date

from pydantic import Field

from server.agent.tools.registry import ToolContext, ToolError, tool
from server.integrations.data_repo.schemas.common import KaModel
from server.integrations.tmdb import ATTRIBUTION, TmdbClient


def _client() -> TmdbClient:
    token = os.environ.get("TMDB_API_TOKEN")
    if not token:
        raise ToolError("movies need TMDB_API_TOKEN in .env")
    return TmdbClient(token)


class SearchArgs(KaModel):
    query: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1890, le=2100)


class DiscoverArgs(KaModel):
    genres: list[int] = []  # TMDB genre ids, e.g. 878 science fiction, 18 drama, 35 comedy
    released_since: date | None = None
    released_until: date | None = None


class WatchArgs(KaModel):
    tmdb_id: int


@tool(
    "movies_search",
    "Find films by title on TMDB. Returns ids, titles, release dates and short overviews.",
    SearchArgs,
    toolkit="movies",
    untrusted=True,
    flag="movies",
    activity="Searched films",
)
def movies_search(args: SearchArgs, ctx: ToolContext):
    return {"movies": _client().search(args.query, args.year), "attribution": ATTRIBUTION}


@tool(
    "movies_discover",
    "Recent and upcoming releases in Canada, newest first, optionally by genre and date range.",
    DiscoverArgs,
    toolkit="movies",
    untrusted=True,
    flag="movies",
    activity="Looked for new films",
)
def movies_discover(args: DiscoverArgs, ctx: ToolContext):
    since = args.released_since or date(ctx.today().year - 1, ctx.today().month, 1)
    found = _client().discover(args.genres, since, args.released_until)
    return {"movies": found, "attribution": ATTRIBUTION}


@tool(
    "movies_where_to_watch",
    "Where a film can legally be watched in Canada: streaming, rental and purchase services.",
    WatchArgs,
    toolkit="movies",
    untrusted=True,
    flag="movies",
    activity="Checked where to watch a film",
)
def movies_where_to_watch(args: WatchArgs, ctx: ToolContext):
    return _client().watch_providers(args.tmdb_id)
