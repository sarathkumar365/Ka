"""load_toolkit: add a pack's tools for the rest of the chat, with its instructions and memory."""

from datetime import datetime

from server.agent.tools.registry import REGISTRY, ToolContext, ToolError, tool
from server.integrations.data_repo.loader import load_memory
from server.integrations.data_repo.schemas.common import KaModel

from ..base import available, instructions, manifests


class LoadToolkitArgs(KaModel):
    name: str


@tool(
    "load_toolkit",
    "Load a toolkit by name (see the toolkit list in your instructions). Its tools stay "
    "available for the rest of this chat; returns its instructions and its memory.",
    LoadToolkitArgs,
    activity="Loaded a toolkit",
)
def load_toolkit(args: LoadToolkitArgs, ctx: ToolContext):
    names = [m.name for m in available(ctx.config)]
    if args.name not in names:
        return {
            "loaded": None,
            "message": f"no toolkit {args.name!r}; available: {', '.join(names) or 'none'}",
        }
    if ctx.db is None or ctx.conversation_id is None:
        raise ToolError("conversation store not available")
    if args.name in ctx.db.loaded_toolkits(ctx.conversation_id):
        return {"loaded": args.name, "message": "already loaded"}
    ctx.db.add_toolkit(ctx.conversation_id, args.name, datetime.now())
    if manifests()[args.name].private:
        ctx.mark_private()  # its memory and tools hold finance data
    memory = [
        f"- {m.id} [{m.type}]: {m.text}"
        for m in load_memory(ctx.config.data_repo, args.name).entries
        if m.status == "active"
    ]
    return {
        "loaded": args.name,
        "instructions": instructions(args.name),
        "memory": memory,
        "tools": sorted(t.name for t in REGISTRY.values() if t.toolkit == args.name),
    }
