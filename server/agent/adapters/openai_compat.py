"""One class for OpenRouter and Ollama: both speak the OpenAI chat API, only base_url differs."""

import os
import time
from collections.abc import Callable, Mapping

import openai

from server.config import ModelConfig

from .base import AdapterError, Reply, ToolCall, Usage

OPENROUTER_URL = "https://openrouter.ai/api/v1"
NO_CREDITS = {"insufficient_quota", "credit_balance_exhausted"}
RETRYABLE = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)


def _retryable(e: Exception) -> bool:
    if isinstance(e, RETRYABLE):
        return True
    return isinstance(e, openai.APIStatusError) and e.status_code >= 500


class OpenAICompatAdapter:
    def __init__(
        self,
        model: str,
        base_url: str | None,
        api_key: str | None,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        max_tries: int = 3,
        zdr: bool = False,
        only: list[str] | None = None,
    ) -> None:
        self.model, self.sleep, self.max_tries, self.zdr = model, sleep, max_tries, zdr
        self.only = only or []
        self.client = client or openai.OpenAI(
            base_url=base_url, api_key=api_key, timeout=60, max_retries=0
        )

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        provider: dict = {}
        if self.zdr:
            provider |= {"zdr": True, "data_collection": "deny"}
        if self.only:
            provider["only"] = self.only
        if provider:
            kwargs["extra_body"] = {"provider": provider}
        for attempt in range(self.max_tries):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                break
            except openai.OpenAIError as e:
                if (
                    getattr(e, "code", None) in NO_CREDITS
                    or getattr(e, "type", None) == "insufficient_quota"
                ):
                    raise AdapterError("provider reports no credits remaining") from None
                if not _retryable(e):
                    # type name only: provider messages can echo headers or keys
                    raise AdapterError(f"model call failed: {type(e).__name__}") from None
                if attempt == self.max_tries - 1:
                    raise AdapterError("model unavailable after retries") from None
                self.sleep(0.5 * 2**attempt)
        if not getattr(resp, "choices", None):
            raise AdapterError("model returned no choices")
        msg = resp.choices[0].message
        calls = [
            ToolCall(c.id, c.function.name, c.function.arguments) for c in (msg.tool_calls or [])
        ]
        u = resp.usage
        usage = Usage(u.prompt_tokens, u.completion_tokens) if u else Usage()
        return Reply(text=msg.content, tool_calls=calls, usage=usage)


def build_adapter(cfg: ModelConfig, env: Mapping[str, str] = os.environ) -> OpenAICompatAdapter:
    if cfg.provider == "openai":
        key = env.get("OPENAI_API_KEY")
        if not key:
            raise AdapterError("OPENAI_API_KEY not set")
        return OpenAICompatAdapter(cfg.model, cfg.base_url, key)
    if cfg.provider == "openrouter":
        key = env.get("OPENROUTER_API_KEY")
        if not key:
            raise AdapterError("OPENROUTER_API_KEY not set")
        return OpenAICompatAdapter(
            cfg.model, cfg.base_url or OPENROUTER_URL, key, zdr=cfg.zdr, only=cfg.only
        )
    return OpenAICompatAdapter(cfg.model, cfg.base_url or "http://localhost:11434/v1", "ollama")
