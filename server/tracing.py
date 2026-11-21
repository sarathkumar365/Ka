"""OpenTelemetry spans for chat turns, model calls and tool calls, exported to Langfuse.

With the `tracing` flag off (or no Langfuse keys) there is no provider and every span is a no-op,
so the loop always calls these helpers.
"""

import base64
import contextvars
import json
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter

from server.config import Config
from server.flags import is_on

DEFAULT_BASE_URL = "http://localhost:3000"
MAX_TEXT = 20_000  # span input and output are capped; a long chat would bloat every trace

_provider: TracerProvider | None = None
_who: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ka_trace_who", default=None)


def langfuse_target(env: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    base = (env.get("LANGFUSE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    pair = f"{env['LANGFUSE_PUBLIC_KEY']}:{env['LANGFUSE_SECRET_KEY']}".encode()
    headers = {
        "Authorization": "Basic " + base64.b64encode(pair).decode(),
        "x-langfuse-ingestion-version": "4",  # without it new data can take minutes to show
    }
    return f"{base}/api/public/otel/v1/traces", headers


def setup_tracing(
    cfg: Config, env: Mapping[str, str] = os.environ, exporter: SpanExporter | None = None
) -> bool:
    global _provider
    if not is_on(cfg, "tracing"):
        return False
    if exporter is None:
        if not env.get("LANGFUSE_PUBLIC_KEY") or not env.get("LANGFUSE_SECRET_KEY"):
            return False
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint, headers = langfuse_target(env)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
    else:
        processor = SimpleSpanProcessor(exporter)
    provider = TracerProvider(resource=Resource.create({"service.name": "ka"}))
    provider.add_span_processor(processor)
    _provider = provider
    return True


def shutdown_tracing() -> None:
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None


def _tracer() -> trace.Tracer:
    # A private provider, not the global one: OpenTelemetry allows setting the global only once.
    return _provider.get_tracer("ka") if _provider else trace.NoOpTracer()


def _clip(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:MAX_TEXT]


def _tag(span, kind: str) -> None:
    span.set_attribute("langfuse.observation.type", kind)
    for key, value in (_who.get() or {}).items():  # Langfuse filters by user and session on every span
        span.set_attribute(key, value)


@contextmanager
def turn_span(
    name: str, user_id: str, conversation_id: str, input: str,
    private: Callable[[], bool] = lambda: False,
) -> Iterator[None]:  # fmt: skip
    """`private` is asked at the end: a chat turns private in the turn that first reads finance."""
    token = _who.set({"langfuse.user.id": user_id, "langfuse.session.id": conversation_id})
    try:
        with _tracer().start_as_current_span("turn") as span:
            _tag(span, "span")
            span.set_attribute("langfuse.trace.name", name)
            try:
                yield
            finally:
                if not private():
                    span.set_attribute("langfuse.observation.input", _clip(input))
    finally:
        _who.reset(token)


@dataclass
class _ToolSpan:
    span: object
    text: str | None = None

    def result(self, text: str) -> None:
        self.text = text


@contextmanager
def tool_span(
    name: str, args: dict, private: Callable[[], bool] = lambda: False
) -> Iterator[_ToolSpan]:
    """Content is attached at the end, and only if the chat is still not private by then."""
    with _tracer().start_as_current_span(f"tool:{name}") as span:
        _tag(span, "tool")
        holder = _ToolSpan(span)
        try:
            yield holder
        finally:
            if not private():
                span.set_attribute("langfuse.observation.input", _clip(args))
                if holder.text is not None:
                    span.set_attribute("langfuse.observation.output", _clip(holder.text))


class TracedAdapter:
    """Wraps any adapter, so every model call (chat, extraction, suggestions, loops) is a span."""

    def __init__(self, inner, task: str, model: str | None = None) -> None:
        self.inner, self.task = inner, task
        self.model = model or getattr(inner, "model", "unknown")

    def complete(self, messages: list[dict], tools: list[dict]):
        with _tracer().start_as_current_span("model") as span:
            _tag(span, "generation")
            span.set_attribute("gen_ai.request.model", self.model)
            span.set_attribute("langfuse.trace.metadata.task", self.task)
            reply = self.inner.complete(messages, tools)
            if self.task != "private":  # private chats hold finance data: counts and timings only
                out = reply.text or json.dumps(
                    [{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls]
                )
                span.set_attribute("langfuse.observation.input", _clip(messages))
                span.set_attribute("langfuse.observation.output", _clip(out))
            u = reply.usage
            span.set_attribute("gen_ai.usage.input_tokens", u.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", u.completion_tokens)
            cached = getattr(u, "cached_tokens", 0)
            if cached:
                span.set_attribute("gen_ai.usage.cache_read_input_tokens", cached)
            cost = getattr(u, "cost_usd", None)
            if cost is not None:
                span.set_attribute("gen_ai.usage.cost", float(cost))
            return reply


def traced_factory(cfg: Config, factory, task: str):
    """Adapter factory that wraps each adapter when tracing is on."""
    if factory is None or not is_on(cfg, "tracing"):
        return factory
    return lambda: TracedAdapter(factory(), task)
