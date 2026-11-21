"""Private model chain: finance conversations go only here, never back to the default model."""

import os
from collections.abc import Mapping

from server.config import Config

from .base import Adapter, AdapterError, Reply
from .openai_compat import build_adapter


class ChainAdapter:
    def __init__(self, adapters: list[Adapter]) -> None:
        self.adapters = adapters

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        reason = "no private model configured"
        for adapter in self.adapters:
            try:
                return adapter.complete(messages, tools)
            except AdapterError as e:
                reason = str(e)
        raise PrivateUnavailable(reason)


class PrivateUnavailable(AdapterError):
    """The finance chain is down. The chat must not fall back to the default model, so say why
    and how to go on."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            "This chat holds finance data, so it only uses the private model, which is not "
            f"available right now ({reason}). Start a new chat for other questions."
        )


def build_private_adapter(cfg: Config, env: Mapping[str, str] = os.environ) -> ChainAdapter:
    return ChainAdapter([build_adapter(m, env) for m in cfg.private_models])
