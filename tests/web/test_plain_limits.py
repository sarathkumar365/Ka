import time

import httpx
import pytest

from server.agent.tools.registry import ToolError
from server.web import plain


class Peer:
    def __init__(self, ip):
        self.ip = ip

    def get_extra_info(self, name):
        return (self.ip, 443) if name == "server_addr" else None


def fetcher(handler):
    return plain.PlainFetcher(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_large_body_stops_at_cap(monkeypatch):
    monkeypatch.setattr(plain, "MAX_BYTES", 1000)

    def endless():
        while True:
            yield b"a" * 100

    page = fetcher(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=endless())).fetch("https://x.example/")
    assert len(page.text) <= 1000


def test_slow_stream_hits_deadline(monkeypatch):
    monkeypatch.setattr(plain, "FETCH_DEADLINE", 0.2)

    def slow():
        while True:
            time.sleep(0.05)
            yield b"a"

    start = time.monotonic()
    with pytest.raises(ToolError, match="page took too long"):
        fetcher(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=slow())).fetch("https://x.example/")
    assert time.monotonic() - start < 1.2


def test_private_peer_is_refused():
    def handler(r):
        return httpx.Response(200, content=b"secret", extensions={"network_stream": Peer("127.0.0.1")})

    with pytest.raises(ToolError, match="private or local"):
        fetcher(handler).fetch("https://rebind.example/")
