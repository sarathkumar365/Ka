from .base import Reply


class FakeAdapter:
    """Scripted replies for tests and evals; records the messages of every call."""

    def __init__(self, replies: list[Reply]) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.tools: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        self.calls.append([dict(m) for m in messages])
        self.tools.append(tools)
        assert self.replies, "FakeAdapter script exhausted"
        return self.replies.pop(0)
