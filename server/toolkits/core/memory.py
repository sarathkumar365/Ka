"""Queue a fact the agent inferred. Nothing is written to memory.yaml until the owner approves."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from server.agent.tools.registry import ToolContext, ToolError, tool
from server.integrations.data_repo.schemas.common import KaModel
from server.memory.pending import PendingError, queue_memory


class ProposeMemoryArgs(KaModel):
    text: str = Field(min_length=1)
    type: Literal["fact", "preference", "rule"] = "fact"
    replaces: str | None = None  # id of an active memory this contradicts
    toolkit: str = Field(default="core", pattern=r"^[a-z]+$")  # which memory file


@tool(
    "propose_memory",
    "Queue a fact, preference or rule you inferred about the owner for their approval. "
    "Use replaces=<memory id> when it contradicts an existing memory. Use remember instead when "
    "the owner explicitly asked you to remember something.",
    ProposeMemoryArgs,
    activity="Suggested a memory",
)
def propose_memory(args: ProposeMemoryArgs, ctx: ToolContext):
    if ctx.db is None:
        raise ToolError("conversation store not available")
    try:
        return queue_memory(
            ctx.db,
            ctx.data,
            args.text,
            args.type,
            args.replaces,
            ctx.conversation_id,
            datetime.now(),
            toolkit=args.toolkit,
        )
    except PendingError as e:
        raise ToolError(str(e)) from e
