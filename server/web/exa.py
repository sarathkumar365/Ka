import httpx

from .providers import (
    FETCH_TIMEOUT,
    PAGE_CHARS,
    SEARCH_TIMEOUT,
    SNIPPET_CHARS,
    Page,
    SearchResult,
    day,
)

URL = "https://api.exa.ai"


class ExaSearch:
    name = "exa"

    def __init__(self, key: str, http: httpx.Client | None = None) -> None:
        self.key, self.http = key, http or httpx.Client(timeout=SEARCH_TIMEOUT)

    def search(self, query: str, limit: int) -> list[SearchResult]:
        body = {
            "query": query,
            "numResults": limit,
            "type": "auto",
            "contents": {"highlights": {"maxCharacters": SNIPPET_CHARS}},
        }
        r = self.http.post(f"{URL}/search", json=body, headers={"x-api-key": self.key})
        r.raise_for_status()
        return [
            SearchResult(
                title=x.get("title") or x["url"], url=x["url"],
                snippet=" ".join(x.get("highlights") or [])[:SNIPPET_CHARS],
                published=day(x.get("publishedDate")), source=self.name,
            )
            for x in r.json().get("results", [])
        ]  # fmt: skip


class ExaFetcher:
    name = "exa"

    def __init__(self, key: str, http: httpx.Client | None = None) -> None:
        self.key, self.http = key, http or httpx.Client(timeout=FETCH_TIMEOUT)

    def fetch(self, url: str) -> Page:
        body = {"urls": [url], "text": {"maxCharacters": PAGE_CHARS * 4}}
        r = self.http.post(f"{URL}/contents", json=body, headers={"x-api-key": self.key})
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            raise ValueError("no content")
        x = results[0]
        return Page(url=url, title=x.get("title") or url, text=x.get("text") or "",
                    published=day(x.get("publishedDate")), truncated=False)  # fmt: skip
