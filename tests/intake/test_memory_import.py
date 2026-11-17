import json
from datetime import datetime

import pytest

from server.agent.adapters import AdapterError
from server.agent.adapters.base import Reply
from server.agent.adapters.fake import FakeAdapter
from server.intake.memory_import import import_memory
from server.intake.readers import IntakeError
from server.integrations.data_repo.loader import load_data
from server.store.db import Db

NOW = datetime(2031, 4, 5, 12, 0)


def test_import_queues_unverified_items_with_replaces(ctx):
    data = load_data(ctx.config.data_repo)
    items = [
        {"type": "preference", "text": "Prefers hybrid roles", "replaces": "M-0001"},
        {"type": "fact", "text": "Speaks French", "replaces": None},
    ]
    db = Db(":memory:")
    n = import_memory(
        "pasted text", "claude", db, data, FakeAdapter([Reply(text=json.dumps(items))]), NOW
    )
    assert n == 2
    first, second = db.list_pending()
    assert first.source == "import:claude"
    assert first.payload["text"].startswith("(imported, unverified) ")
    assert first.payload["replaces"] == "M-0001" and second.payload["replaces"] is None


def test_import_failure_is_readable(ctx):
    class Down:
        def complete(self, messages, tools):
            raise AdapterError("provider reports no credits remaining")

    with pytest.raises(IntakeError, match="no credits"):
        import_memory("x", "claude", Db(":memory:"), load_data(ctx.config.data_repo), Down(), NOW)
