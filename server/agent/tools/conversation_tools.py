"""Read tool over saved conversations."""

from dataclasses import asdict

from pydantic import Field

from server.integrations.data_repo.schemas.common import KaModel

from .registry import ToolContext, ToolError, tool


class ConversationSearchArgs(KaModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


@tool(
    "search_conversations",
    "Keyword search across past chats with the owner. Returns snippets with conversation ids.",
    ConversationSearchArgs,
)
def search_conversations(args: ConversationSearchArgs, ctx: ToolContext):
    if ctx.db is None:
        raise ToolError("conversation store not available")
    return {"hits": [asdict(h) for h in ctx.db.search(args.query, args.limit)]}
