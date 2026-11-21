import threading
from collections import deque
from datetime import datetime, timedelta


class LoginLimiter:
    """Events per key in a sliding window, in memory. Keys are an address, or address|username."""

    def __init__(
        self, max_attempts: int = 20, window: timedelta = timedelta(minutes=10),
        max_keys: int = 10_000,
    ) -> None:  # fmt: skip
        self.max, self.window, self.max_keys = max_attempts, window, max_keys
        self._seen: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: datetime) -> deque[datetime]:
        q = self._seen.get(key) or deque()
        while q and now - q[0] >= self.window:
            q.popleft()
        if q:
            self._seen[key] = q
        else:
            self._seen.pop(key, None)  # empty keys are dropped, so memory stays bounded
        return q

    def _store(self, key: str, q: deque[datetime], now: datetime) -> None:
        """Keep the key; at the cap, drop expired keys first, then the oldest ones."""
        self._seen.pop(key, None)  # re-insert so dict order is last-used order
        if len(self._seen) >= self.max_keys:
            for k in [k for k, v in self._seen.items() if not v or now - v[-1] >= self.window]:
                del self._seen[k]
            while len(self._seen) >= self.max_keys:
                del self._seen[next(iter(self._seen))]
        self._seen[key] = q

    def allow(self, key: str, now: datetime) -> bool:
        """Count an attempt; False once the key used up its window."""
        with self._lock:
            q = self._recent(key, now)
            if len(q) >= self.max:
                return False
            q.append(now)
            self._store(key, q, now)
            return True

    def fail(self, key: str, now: datetime) -> None:
        with self._lock:
            q = self._recent(key, now)
            q.append(now)
            self._store(key, q, now)

    def blocked(self, key: str, now: datetime) -> bool:
        with self._lock:
            return len(self._recent(key, now)) >= self.max

    def clear(self, key: str) -> None:
        with self._lock:
            self._seen.pop(key, None)
