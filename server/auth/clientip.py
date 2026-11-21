"""The real client address. Ka sits behind the tailnet proxy, which connects from loopback."""

TRUSTED = frozenset({"127.0.0.1", "::1"})


def trusted_proxy(request) -> bool:
    peer = request.client.host if request.client else ""
    return peer in getattr(request.app.state, "trusted_proxies", TRUSTED)


def client_ip(request) -> str:
    """X-Forwarded-For is believed only from the local proxy, and only its last entry: the proxy
    appends the real address after whatever the client sent, so earlier entries are forgeable."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and trusted_proxy(request):
        return forwarded.split(",")[-1].strip() or peer
    return peer
