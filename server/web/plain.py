import httpx

from .clean import html_to_text
from .providers import FETCH_TIMEOUT, Page, check_public_url

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3


class PlainFetcher:
    """Last resort with no key: GET the page and strip it to text."""

    name = "plain"

    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(
            timeout=FETCH_TIMEOUT, follow_redirects=False, headers={"User-Agent": "ka-agent"}
        )

    def fetch(self, url: str) -> Page:
        # Redirects are followed by hand so every hop passes the public-address check.
        for _ in range(MAX_REDIRECTS + 1):
            r = self.http.get(url)
            if not r.is_redirect:
                break
            url = str(r.url.join(r.headers["location"]))
            check_public_url(url)
        else:
            raise ValueError("too many redirects")
        r.raise_for_status()
        body = r.content[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
        if "html" in r.headers.get("content-type", "html"):
            title, text = html_to_text(body)
        else:
            title, text = url, body
        return Page(url=url, title=title or url, text=text, published=None, truncated=False)
