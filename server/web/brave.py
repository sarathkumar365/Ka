import httpx

from .providers import SEARCH_TIMEOUT, SNIPPET_CHARS, SearchResult, day

URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearch:
    name = "brave"

    def __init__(self, key: str, http: httpx.Client | None = None) -> None:
        self.key, self.http = key, http or httpx.Client(timeout=SEARCH_TIMEOUT)

    def search(self, query: str, limit: int) -> list[SearchResult]:
        r = self.http.get(
            URL, params={"q": query, "count": limit},
            headers={"X-Subscription-Token": self.key, "Accept": "application/json"},
        )  # fmt: skip
        r.raise_for_status()
        return [
            SearchResult(
                title=x.get("title") or x["url"], url=x["url"],
                snippet=(x.get("description") or "")[:SNIPPET_CHARS],
                published=day(x.get("page_age")), source=self.name,
            )
            for x in (r.json().get("web") or {}).get("results", [])
        ]  # fmt: skip
