import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta


class LoginLimiter:
    """Login attempts per client in a sliding window, in memory (one process, one owner)."""

    def __init__(self, max_attempts: int = 20, window: timedelta = timedelta(minutes=10)) -> None:
        self.max, self.window = max_attempts, window
        self._seen: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str, now: datetime) -> bool:
        with self._lock:
            q = self._seen[client]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.max:
                return False
            q.append(now)
            return True
