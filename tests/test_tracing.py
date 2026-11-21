from datetime import datetime

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from server import tracing
from server.agent.adapters import FakeAdapter, Reply, ToolCall
from server.agent.adapters.base import Usage
from server.agent.loop import run_turn
from server.store.db import Db

NOW = lambda: datetime(2031, 4, 5, 12, 0)


@pytest.fixture
def memory_exporter(ctx):
    exporter = InMemorySpanExporter()
    cfg = ctx.config.model_copy(update={"flags": {"tracing": True}})
    assert tracing.setup_tracing(cfg, env={}, exporter=exporter) is True
    yield exporter
    tracing.shutdown_tracing()


def test_turn_model_and_tool_spans_nest(ctx, memory_exporter):
    ctx.db = Db(":memory:", "avery")
    cid = ctx.db.new_conversation(NOW())
    replies = [
        Reply(tool_calls=[ToolCall("1", "get_profile", "{}")], usage=Usage(10, 2)),
        Reply(text="ok", usage=Usage(12, 1)),
    ]
    adapter = tracing.TracedAdapter(FakeAdapter(replies), task="chat")
    run_turn("who am I", conv_id=cid, db=ctx.db, adapter=adapter, ctx=ctx, approve=lambda p: True, now=NOW)
    spans = memory_exporter.get_finished_spans()
    by = {s.name: s for s in spans}
    assert {"turn", "model", "tool:get_profile"} <= by.keys()
    assert by["model"].parent.span_id == by["turn"].context.span_id
    assert by["tool:get_profile"].parent.span_id == by["turn"].context.span_id
    assert by["model"].attributes["langfuse.session.id"] == cid
    assert by["turn"].attributes["langfuse.user.id"] == "avery"
    assert by["model"].attributes["langfuse.observation.type"] == "generation"
    assert sum(s.attributes.get("gen_ai.usage.input_tokens", 0) for s in spans) == 22


def test_tracing_off_records_nothing(ctx):
    assert tracing.setup_tracing(ctx.config, env={}) is False


def test_tracing_on_without_keys_stays_off(ctx):
    cfg = ctx.config.model_copy(update={"flags": {"tracing": True}})
    assert tracing.setup_tracing(cfg, env={}) is False


def test_exporter_headers_for_langfuse(ctx):
    env = {"LANGFUSE_PUBLIC_KEY": "pk-lf-1", "LANGFUSE_SECRET_KEY": "sk-lf-2"}
    endpoint, headers = tracing.langfuse_target(env)
    assert endpoint == "http://localhost:3000/api/public/otel/v1/traces"
    assert headers["Authorization"] == "Basic cGstbGYtMTpzay1sZi0y"
    assert headers["x-langfuse-ingestion-version"] == "4"
