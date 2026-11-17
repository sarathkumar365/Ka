"""Tool registry: name, description, validated args, READ or WRITE, and the approval seam."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from server.config import Config
from server.finance.store import FinanceStore
from server.integrations.data_repo.loader import KaData, load_data
from server.integrations.data_repo.schemas.common import KaModel
from server.store.db import Db


class ToolError(Exception):
    """The message goes back to the model as the tool result."""


@dataclass
class PendingWrite:
    summary: str
    diff: str
    apply: Callable[[], str]  # performs the write, returns a one-line result


@dataclass
class ToolContext:
    config: Config
    store: FinanceStore
    today: Callable[[], date] = date.today
    db: Db | None = None
    conversation_id: str | None = None

    def mark_private(self) -> None:
        """The result holds finance data: move this conversation to the private model."""
        if self.db is not None and self.conversation_id is not None:
            self.db.mark_private(self.conversation_id)

    @property
    def data(self) -> KaData:
        # Reloaded each time so a committed change is visible at once; the files are small.
        return load_data(self.config.data_repo)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[KaModel]
    fn: Callable[[Any, ToolContext], Any]
    mode: Literal["READ", "WRITE"]
    approval: bool  # True: fn returns a PendingWrite for the loop to show and apply
    private: bool = False  # result holds finance data: the conversation moves to the private model


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    args_model: type[KaModel],
    mode: Literal["READ", "WRITE"] = "READ",
    approval: bool = False,
    private: bool = False,
):
    def register(fn: Callable[[Any, ToolContext], Any]):
        if name in REGISTRY:
            raise ValueError(f"tool already registered: {name}")
        REGISTRY[name] = Tool(name, description, args_model, fn, mode, approval, private)
        return fn

    return register


def to_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_json(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal: keep money exact as a string
        return str(value)
    return value


def run_tool(name: str, raw_args: dict, ctx: ToolContext) -> Any:
    t = REGISTRY.get(name)
    if t is None:
        raise ToolError(f"unknown tool: {name}")
    try:
        args = t.args_model(**raw_args)
    except ValidationError as e:
        details = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        raise ToolError(f"invalid arguments for {name}: {details}") from e
    result = t.fn(args, ctx)
    if t.approval:
        if not isinstance(result, PendingWrite):
            raise TypeError(f"{name} is approval-gated and must return PendingWrite")
        return result
    return to_json(result)
