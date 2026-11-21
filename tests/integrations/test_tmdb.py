from datetime import date

import httpx
import pytest

from server.integrations.tmdb import TmdbClient

PROVIDERS = {
    "id": 603,
    "results": {
        "CA": {"link": "https://www.themoviedb.org/movie/603/watch?locale=CA",
               "flatrate": [{"provider_name": "Crave"}], "rent": [{"provider_name": "Apple TV"}]},
        "US": {"flatrate": [{"provider_name": "Max"}]},
    },
}
DISCOVER = {"results": [{"id": 1, "title": "Dune Three", "release_date": "2031-03-01",
                         "overview": "Sand.", "genre_ids": [878], "vote_average": 7.9}]}


class Recorder:
    def __init__(self):
        self.last = None

    def __call__(self, request):
        self.last = request
        if request.url.path.endswith("/watch/providers"):
            return httpx.Response(200, json=PROVIDERS)
        return httpx.Response(200, json=DISCOVER)


@pytest.fixture
def rec():
    return Recorder()


def client(rec):
    return TmdbClient("tok", http=httpx.Client(transport=httpx.MockTransport(rec)))


def test_where_to_watch_reads_canada(rec):
    a = client(rec).watch_providers(603)
    assert a.flatrate == ["Crave"] and a.rent == ["Apple TV"] and a.buy == []
    assert "JustWatch" in a.attribution and rec.last.headers["authorization"] == "Bearer tok"


def test_discover_sends_date_and_region(rec):
    movies = client(rec).discover([878], date(2031, 1, 1), None)
    params = rec.last.url.params
    assert params["primary_release_date.gte"] == "2031-01-01" and params["region"] == "CA"
    assert params["with_genres"] == "878" and "primary_release_date.lte" not in params
    assert movies[0].title == "Dune Three" and movies[0].tmdb_id == 1


def test_search_passes_year(rec):
    client(rec).search("dune", 2031)
    assert rec.last.url.path == "/3/search/movie" and rec.last.url.params["year"] == "2031"
