from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from server.agent.adapters.fake import FakeAdapter
from server.api.app import create_app
from server.store.db import Db


@pytest.fixture
def cfg(ctx):
    return ctx.config


@pytest.fixture
def make_client(cfg):
    def make(replies=(), factory=None, **kw) -> TestClient:
        app = create_app(cfg, factory or (lambda: FakeAdapter(list(replies))), **kw)
        client = TestClient(app, base_url="http://localhost")
        client.app_state = app.state
        return client

    return make


@pytest.fixture
def db(cfg) -> Db:
    return Db(cfg.db_path)


NOW = datetime(2031, 4, 5, 12, 0)
