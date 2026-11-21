"""TMDB API v3 with the read access token. Where-to-watch data comes from JustWatch via TMDB."""

from dataclasses import dataclass, field
from datetime import date

import httpx

BASE = "https://api.themoviedb.org/3"
TIMEOUT = 10.0
ATTRIBUTION = "Data from TMDB; where-to-watch from JustWatch."


@dataclass
class Movie:
    tmdb_id: int
    title: str
    release_date: str | None
    overview: str
    genre_ids: list[int] = field(default_factory=list)
    vote_average: float | None = None


@dataclass
class Availability:
    tmdb_id: int
    region: str
    link: str | None
    flatrate: list[str]
    rent: list[str]
    buy: list[str]
    attribution: str = ATTRIBUTION


def _movie(x: dict) -> Movie:
    return Movie(
        tmdb_id=x["id"], title=x.get("title") or x.get("original_title") or "",
        release_date=x.get("release_date") or None, overview=(x.get("overview") or "")[:500],
        genre_ids=x.get("genre_ids") or [], vote_average=x.get("vote_average"),
    )  # fmt: skip


class TmdbClient:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(timeout=TIMEOUT)
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict) -> dict:
        r = self.http.get(f"{BASE}{path}", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def search(self, query: str, year: int | None = None) -> list[Movie]:
        params: dict = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        return [_movie(x) for x in self._get("/search/movie", params).get("results", [])[:10]]

    def discover(
        self, genres: list[int], since: date | None, until: date | None, region: str = "CA"
    ) -> list[Movie]:
        params: dict = {
            "region": region, "sort_by": "primary_release_date.desc", "vote_count.gte": 20,
            "include_adult": "false",
        }  # fmt: skip
        if genres:
            params["with_genres"] = ",".join(str(g) for g in genres)
        if since:
            params["primary_release_date.gte"] = since.isoformat()
        if until:
            params["primary_release_date.lte"] = until.isoformat()
        return [_movie(x) for x in self._get("/discover/movie", params).get("results", [])[:10]]

    def watch_providers(self, tmdb_id: int, region: str = "CA") -> Availability:
        here = (
            self._get(f"/movie/{tmdb_id}/watch/providers", {}).get("results", {}).get(region) or {}
        )

        def names(kind: str) -> list[str]:
            return [p["provider_name"] for p in here.get(kind) or []]

        return Availability(
            tmdb_id, region, here.get("link"), names("flatrate"), names("rent"), names("buy")
        )
