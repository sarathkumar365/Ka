"""Approval round trip: the loop thread waits here until the browser answers."""

import secrets
import threading


class ApprovalBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: dict[str, tuple[threading.Event, list[bool]]] = {}

    def request(self) -> str:
        approval_id = secrets.token_hex(8)
        with self._lock:
            self._open[approval_id] = (threading.Event(), [False])
        return approval_id

    def wait(self, approval_id: str, timeout: float) -> bool:
        event, answer = self._open[approval_id]
        event.wait(timeout)
        with self._lock:
            self._open.pop(approval_id, None)
        return answer[0]

    def resolve(self, approval_id: str, approve: bool) -> bool:
        with self._lock:
            entry = self._open.get(approval_id)
            if entry is None or entry[0].is_set():
                return False
            entry[1][0] = approve
            entry[0].set()
            return True

    def open_ids(self) -> list[str]:
        with self._lock:
            return list(self._open)

    def cancel_all(self, ids: list[str]) -> None:
        for i in ids:
            self.resolve(i, False)
