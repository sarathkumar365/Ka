# Flow: toolkits and tool safety

**Summary.** Ka is one agent with a small core that is always loaded and packs (toolkits) it loads only when a request needs them: finance and movies today. Each toolkit is a folder with a manifest, its tools, a short instruction file, and a memory file in the owner's data repo; the model always sees each toolkit's one-line description and calls `load_toolkit` to add one for the rest of the chat. Every tool declares in code its toolkit, a risk label (safe or risky) and whether its result is untrusted outside text, so a tricked model cannot change what a tool is allowed to do.

```mermaid
flowchart LR
    P[system prompt: toolkit index] --> M[model]
    M -->|load_toolkit finance| L[conversation_toolkits row]
    L --> V[visible_tools: core + loaded, flags applied]
    V -->|tool_specs| M
    L --> R[result: instructions + memory/finance.yaml + tool names]
    M -->|tool call| C{in visible set?}
    C -->|no| U[error: unknown tool]
    C -->|yes| E[_execute]
```

## Worked example

"How much did I spend in October?" The system prompt lists `- finance: Bank statements and spending ...` (`server/toolkits/finance/manifest.yaml`, read by `base.manifests`). The first model call gets only core tools. The model calls `load_toolkit` (`server/toolkits/core/toolkit.py`): it checks the toolkit is available (`base.available`: exists, flag on), records it in SQLite (`Db.add_toolkit`), marks the chat private because the finance manifest says `private: true`, and returns the toolkit's `instructions.md`, the active entries of `users/<id>/memory/finance.yaml` and its tool names. Before every model call `run_turn` asks `visible_tools(cfg, db.loaded_toolkits(conv))` for the specs, so the finance tools appear from the next step on and stay for the rest of the chat. A call to a tool outside that set returns `error: unknown tool: <name>` without running.

Instructions and memory arrive as a tool result, not in the system prompt, so the system prompt is identical on every call of the chat and prompt caching keeps working.

## Tool definition

`@tool(name, description, ArgsModel, toolkit=..., risk=..., approval=..., untrusted=..., private=..., flag=..., activity=...)` in `server/agent/tools/registry.py`. Rules checked at registration: tools outside core carry the `<toolkit>_` prefix; a tool that returns a `PendingWrite` for approval must be `risky`. `activity` is the activity-log sentence (`server/api/describe.py`). Risky today: `propose_change`, `remember`, `finance_import_statement`. Untrusted today: `finance_search_transactions`, `finance_import_statement` (statement text).

## Untrusted content

An untrusted tool's JSON result goes to the model wrapped as `<untrusted source="tool">...</untrusted>` (`loop.wrap_untrusted`; the payload cannot close the tag early), and the prompt says text inside is data. `run_turn` keeps a per-turn `tainted` flag: once an untrusted tool has run, any risky call returns `blocked: untrusted content was read this turn; ask the owner to confirm in a new message` and an activity line `Blocked <tool> after untrusted content`. A risky call is also blocked when another call in the same reply reads untrusted content, even if listed first, because the model planned both together. A call never taints itself, so a statement import (risky and untrusted) still reaches its approval card. The next owner message starts a clean turn.

## Why this way

- **Packs instead of one long tool list.** Fewer tools per call means better tool choice and cheaper calls; a one-line index keeps the model aware of what it can load (like Claude's Skills).
- **Labels in code.** The loop reads risk and toolkit from `REGISTRY`, never from the model's reply.
- **Toolkit memory in the data repo**, not the code folder, because the code repo is public.

## Failure cases

| Case | Result |
|---|---|
| Unknown or flagged-off toolkit | `load_toolkit` answers with the available names |
| Flag turned off while loaded | its tools leave the specs on the next call; calls are refused |
| Model calls an unloaded tool | `error: unknown tool: <name>` |

Source: `server/toolkits/*`, `server/agent/tools/registry.py`, `server/agent/loop.py`, `server/api/describe.py`
