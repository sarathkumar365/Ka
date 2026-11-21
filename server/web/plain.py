import ipaddress
import time

import httpx

from server.agent.tools.registry import ToolError

from .clean import html_to_text
from .providers import FETCH_TIMEOUT, Page, check_public_url

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
FETCH_DEADLINE = 20.0  # seconds for the whole page; FETCH_TIMEOUT alone is per read


def _check_peer(r: httpx.Response) -> None:
    """The name was checked before connecting; check the address actually reached too, so a
    name that answers public first and local second (DNS rebinding) cannot reach the LAN."""
    stream = r.extensions.get("network_stream")
    addr = stream.get_extra_info("server_addr") if stream is not None else None
    if addr:
        ip = ipaddress.ip_address(addr[0])
        if not ip.is_global or ip.is_multicast:
            raise ToolError("that address is private or local; Ka only reads public pages")


class PlainFetcher:
    """Last resort with no key: GET the page and strip it to text."""

    name = "plain"

    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(
            timeout=FETCH_TIMEOUT, follow_redirects=False, headers={"User-Agent": "ka-agent"}
        )

    def fetch(self, url: str) -> Page:
        deadline = time.monotonic() + FETCH_DEADLINE
        # Redirects are followed by hand so every hop passes the public-address check.
        for _ in range(MAX_REDIRECTS + 1):
            with self.http.stream("GET", url) as r:
                _check_peer(r)
                if r.is_redirect:
                    url = str(r.url.join(r.headers["location"]))
                    check_public_url(url)
                    continue
                r.raise_for_status()
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
                    if time.monotonic() > deadline:
                        raise ToolError("page took too long")
                text = bytes(body[:MAX_BYTES]).decode(r.encoding or "utf-8", errors="replace")
                kind = r.headers.get("content-type", "html")
            break
        else:
            raise ValueError("too many redirects")
        if "html" in kind:
            title, text = html_to_text(text)
        else:
            title = url
        return Page(url=url, title=title or url, text=text, published=None, truncated=False)
