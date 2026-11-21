"""The data repo's one commit lock, and per-account locks for everything else."""

import fcntl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def repo_lock(repo_root: Path) -> Iterator[None]:
    """All accounts share one git repo, so every commit takes this one lock."""
    with open(repo_root / ".ka.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


_user_locks: dict[tuple[str, str], threading.Lock] = {}
_guard = threading.Lock()


def user_lock(name: str, user_id: str) -> threading.Lock:
    """One lock per job and account: one account's slow work never blocks another's."""
    with _guard:
        return _user_locks.setdefault((name, user_id), threading.Lock())
