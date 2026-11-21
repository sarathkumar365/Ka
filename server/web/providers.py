"""Provider order Exa, Brave, Firecrawl for search; Exa, Firecrawl, plain GET for pages."""

import ipaddress
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from server.agent.tools.registry import ToolError

SEARCH_TIMEOUT = 8.0
FETCH_TIMEOUT = 15.0
SNIPPET_CHARS = 400
PAGE_CHARS = 12_000
MAX_RESULTS = 5


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published: str | None  # YYYY-MM-DD when the provider knows it
    source: str  # provider name


@dataclass
class Page:
    url: str
    title: str
    text: str
    published: str | None
    truncated: bool


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[SearchResult]: ...


class PageFetcher(Protocol):
    name: str

    def fetch(self, url: str) -> Page: ...


def day(value: str | None) -> str | None:
    """Provider dates vary (ISO with time, plain date); keep the date part only."""
    return value[:10] if value and len(value) >= 10 and value[4] == "-" else None


def _reason(e: Exception) -> str:
    if isinstance(e, httpx.TimeoutException):
        return "timeout"
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    return type(e).__name__


def providers_from_env(env: Mapping[str, str]) -> tuple[list[SearchProvider], list[PageFetcher]]:
    from .brave import BraveSearch
    from .exa import ExaFetcher, ExaSearch
    from .firecrawl import FirecrawlFetcher, FirecrawlSearch
    from .plain import PlainFetcher

    searchers: list[SearchProvider] = []
    fetchers: list[PageFetcher] = []
    if env.get("EXA_API_KEY"):
        searchers.append(ExaSearch(env["EXA_API_KEY"]))
        fetchers.append(ExaFetcher(env["EXA_API_KEY"]))
    if env.get("BRAVE_SEARCH_API_KEY"):
        searchers.append(BraveSearch(env["BRAVE_SEARCH_API_KEY"]))
    if env.get("FIRECRAWL_API_KEY"):
        searchers.append(FirecrawlSearch(env["FIRECRAWL_API_KEY"]))
        fetchers.append(FirecrawlFetcher(env["FIRECRAWL_API_KEY"]))
    fetchers.append(PlainFetcher())
    return searchers, fetchers


def web_search(
    query: str, limit: int = MAX_RESULTS, providers: list[SearchProvider] | None = None
) -> list[SearchResult]:
    if providers is None:
        import os

        providers = providers_from_env(os.environ)[0]
    if not providers:
        raise ToolError("no web search provider configured (add a key to .env)")
    limit = max(1, min(limit, MAX_RESULTS))
    failures = []
    for p in providers:
        try:
            found = p.search(query, limit)
        except Exception as e:  # noqa: BLE001  any provider failure falls through to the next
            failures.append(f"{p.name}: {_reason(e)}")
            continue
        return [replace(r, snippet=r.snippet[:SNIPPET_CHARS], source=p.name) for r in found[:limit]]
    raise ToolError("web search unavailable: " + "; ".join(failures))


def check_public_url(url: str) -> None:
    """Only http(s) to public addresses: a page must not make Ka read its own API or the LAN."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolError("only http and https links can be read")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ToolError(f"cannot resolve {parts.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:  # also shared space (100.64/10, the tailnet)
            raise ToolError("that address is private or local; Ka only reads public pages")


def fetch_page(
    url: str,
    fetchers: list[PageFetcher] | None = None,
    summarise: Callable[[str], str] | None = None,
) -> Page:
    check_public_url(url)
    if fetchers is None:
        import os

        fetchers = providers_from_env(os.environ)[1]
    failures = []
    for f in fetchers:
        try:
            page = f.fetch(url)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{f.name}: {_reason(e)}")
            continue
        if len(page.text) > PAGE_CHARS:
            short = None
            if summarise is not None:
                try:
                    short = summarise(page.text[: PAGE_CHARS * 4])
                except Exception:  # noqa: BLE001  a failed summary falls back to cutting
                    short = None
            page = replace(page, text=(short or page.text[:PAGE_CHARS]), truncated=True)
        return page
    raise ToolError("could not read the page: " + "; ".join(failures))
