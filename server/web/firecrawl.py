import httpx

from .providers import FETCH_TIMEOUT, SEARCH_TIMEOUT, SNIPPET_CHARS, Page, SearchResult

URL = "https://api.firecrawl.dev/v2"


class FirecrawlSearch:
    name = "firecrawl"

    def __init__(self, key: str, http: httpx.Client | None = None) -> None:
        self.key, self.http = key, http or httpx.Client(timeout=SEARCH_TIMEOUT)

    def search(self, query: str, limit: int) -> list[SearchResult]:
        r = self.http.post(
            f"{URL}/search", json={"query": query, "limit": limit},
            headers={"Authorization": f"Bearer {self.key}"},
        )  # fmt: skip
        r.raise_for_status()
        web = (r.json().get("data") or {}).get("web") or []
        return [
            SearchResult(
                title=x.get("title") or x["url"], url=x["url"],
                snippet=(x.get("description") or "")[:SNIPPET_CHARS], published=None,
                source=self.name,
            )
            for x in web
        ]  # fmt: skip


class FirecrawlFetcher:
    name = "firecrawl"

    def __init__(self, key: str, http: httpx.Client | None = None) -> None:
        self.key, self.http = key, http or httpx.Client(timeout=FETCH_TIMEOUT)

    def fetch(self, url: str) -> Page:
        r = self.http.post(
            f"{URL}/scrape", json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            headers={"Authorization": f"Bearer {self.key}"},
        )  # fmt: skip
        r.raise_for_status()
        data = r.json().get("data") or {}
        meta = data.get("metadata") or {}
        return Page(url=url, title=meta.get("title") or url, text=data.get("markdown") or "",
                    published=None, truncated=False)  # fmt: skip
