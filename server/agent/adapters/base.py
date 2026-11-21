"""Provider-neutral model interface. The loop only ever sees these types."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


class AdapterError(Exception):
    """Safe to show the owner: never contains keys or raw provider messages."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text; the loop parses it so bad JSON becomes a tool error


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: Decimal | None = None  # OpenRouter reports it; others leave it empty


@dataclass
class Reply:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


class Adapter(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> Reply: ...


def tool_specs(tools) -> list[dict]:
    """JSON tool specs for the model, from Tool objects (or a name -> Tool dict)."""
    if isinstance(tools, dict):
        tools = tools.values()
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.args_model.model_json_schema(),
            },
        }
        for t in tools
    ]
