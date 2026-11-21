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
        self.last = kwargs
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


def test_zdr_sends_provider_options():
    client = FakeClient([good()])
    a = OpenAICompatAdapter("m", None, "k", client=client, zdr=True)
    a.complete([{"role": "user", "content": "x"}], [])
    assert client.last["extra_body"] == {"provider": {"zdr": True, "data_collection": "deny"}}


def test_chain_falls_through_then_fails():
    from server.agent.adapters.chain import ChainAdapter

    class Down:
        def complete(self, messages, tools):
            raise AdapterError("down")

    ok = OpenAICompatAdapter("m", None, "k", client=FakeClient([good()]))
    assert ChainAdapter([Down(), ok]).complete([], []).text == "hi"
    with pytest.raises(AdapterError, match="only uses the private model"):
        ChainAdapter([Down(), Down()]).complete([], [])


def test_private_models_config_and_builder():
    from server.agent.adapters.chain import build_private_adapter
    from server.config import Config

    cfg = Config(
        data_repo=".",
        private_models=[{"provider": "openrouter", "model": "m", "zdr": True}],
    )
    chain = build_private_adapter(cfg, env={"OPENROUTER_API_KEY": "k"})
    assert chain.adapters[0].zdr is True


@pytest.mark.parametrize(
    "entry",
    [{"provider": "openai", "model": "m"}, {"provider": "openrouter", "model": "m"}],
)
def test_private_models_must_keep_no_data(entry):
    from pydantic import ValidationError

    from server.config import Config

    with pytest.raises(ValidationError):
        Config(data_repo=".", private_models=[entry])
    Config(data_repo=".", private_models=[{"provider": "ollama", "model": "m"}])


def test_only_pins_providers():
    client = FakeClient([good()])
    a = OpenAICompatAdapter("m", None, "k", client=client, zdr=True, only=["amazon-bedrock"])
    a.complete([], [])
    assert client.last["extra_body"]["provider"]["only"] == ["amazon-bedrock"]


def test_fallbacks_cache_and_reasoning_reach_the_body():
    fake = FakeClient([good()])
    a = OpenAICompatAdapter(
        "m1", None, "k", client=fake, fallbacks=["m2"], cache=True, reasoning="high"
    )
    a.complete([{"role": "system", "content": "S"}, {"role": "user", "content": "u"}], [])
    body = fake.last
    assert body["extra_body"]["models"] == ["m1", "m2"]
    assert body["extra_body"]["reasoning"] == {"effort": "high"}
    assert body["messages"][0]["content"][0] == {
        "type": "text", "text": "S", "cache_control": {"type": "ephemeral"}
    }
    assert body["messages"][1] == {"role": "user", "content": "u"}


def test_usage_cost_and_cache_hits_are_read():
    from decimal import Decimal

    resp = good()
    resp.usage = NS(prompt_tokens=900, completion_tokens=5, cost=0.0012,
                    prompt_tokens_details=NS(cached_tokens=800))
    r = OpenAICompatAdapter("m", None, "k", client=FakeClient([resp])).complete([], [])
    assert r.usage.cost_usd == Decimal("0.0012") and r.usage.cached_tokens == 800


def test_plain_usage_has_no_cost():
    r = OpenAICompatAdapter("m", None, "k", client=FakeClient([good()])).complete([], [])
    assert r.usage.cost_usd is None and r.usage.cached_tokens == 0


def test_small_and_grader_fall_back_to_default():
    from pathlib import Path

    from server.config import Config

    cfg = Config(data_repo=Path("/x"), models={"default": ModelConfig(provider="ollama", model="d")})
    assert cfg.model_for("small").model == "d" and cfg.model_for("chat").model == "d"
    cfg2 = cfg.model_copy(update={"models": {**cfg.models, "grader": ModelConfig(provider="ollama", model="g")}})
    assert cfg2.model_for("grader").model == "g"


def test_fallbacks_need_openrouter():
    with pytest.raises(ValueError):
        ModelConfig(provider="openai", model="m", fallbacks=["x"])
