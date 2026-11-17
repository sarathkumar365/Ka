from types import SimpleNamespace as NS

import httpx2 as httpx
import openai
import pytest

from server.agent.adapters.base import AdapterError
from server.agent.adapters.openai_compat import OpenAICompatAdapter, build_adapter
from server.config import ModelConfig

REQ = httpx.Request("POST", "http://x/v1/chat/completions")


def rate_limit():
    return openai.RateLimitError("slow", response=httpx.Response(429, request=REQ), body=None)


def auth_error():
    return openai.AuthenticationError(
        "bad key sk-secret", response=httpx.Response(401, request=REQ), body=None
    )


def good(tool_calls=None):
    msg = NS(content="hi", tool_calls=tool_calls)
    return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=3, completion_tokens=2))


class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def adapter(script, sleeps):
    return OpenAICompatAdapter(
        "m", None, "sk-secret", client=FakeClient(script), sleep=sleeps.append
    )


def test_retries_rate_limit_then_succeeds():
    sleeps = []
    reply = adapter([rate_limit(), rate_limit(), good()], sleeps).complete([], [])
    assert reply.text == "hi" and len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_auth_error_fails_at_once_and_message_hides_key():
    sleeps = []
    with pytest.raises(AdapterError) as e:
        adapter([auth_error()], sleeps).complete([], [])
    assert not sleeps and "sk-secret" not in str(e.value)


def test_gives_up_after_max_tries_with_clear_message():
    timeout = openai.APITimeoutError(request=REQ)
    with pytest.raises(AdapterError, match="unavailable"):
        adapter([timeout] * 3, []).complete([], [])


def test_maps_tool_calls_and_usage():
    calls = [
        NS(id="c1", function=NS(name="get_profile", arguments="{}")),
        NS(id="c2", function=NS(name="get_jobs", arguments='{"include_retired": true}')),
    ]
    reply = adapter([good(calls)], []).complete([], [])
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("c1", "get_profile", "{}"),
        ("c2", "get_jobs", '{"include_retired": true}'),
    ]
    assert reply.usage.prompt_tokens == 3


def test_openrouter_needs_key_in_env():
    cfg = ModelConfig(provider="openrouter", model="m")
    with pytest.raises(AdapterError, match="OPENROUTER_API_KEY"):
        build_adapter(cfg, env={})


def test_sdk_level_retries_are_off_so_calls_cannot_multiply():
    a = build_adapter(ModelConfig(provider="ollama", model="m"))
    assert a.client.max_retries == 0


def test_reply_without_choices_is_an_adapter_error():
    empty = NS(choices=[], usage=None)
    with pytest.raises(AdapterError, match="no choices"):
        adapter([empty], []).complete([], [])


def test_openai_provider_needs_its_own_key_and_uses_default_endpoint():
    cfg = ModelConfig(provider="openai", model="m")
    with pytest.raises(AdapterError, match="OPENAI_API_KEY"):
        build_adapter(cfg, env={})
    a = build_adapter(cfg, env={"OPENAI_API_KEY": "sk-x"})
    assert "openai.com" in str(a.client.base_url)


def test_out_of_credits_fails_at_once_with_a_clear_message():
    broke = openai.RateLimitError(
        "no credits",
        response=httpx.Response(429, request=REQ),
        body={"code": "credit_balance_exhausted", "type": "insufficient_quota", "message": "x"},
    )
    sleeps = []
    with pytest.raises(AdapterError, match="no credits"):
        adapter([broke], sleeps).complete([], [])
    assert not sleeps
