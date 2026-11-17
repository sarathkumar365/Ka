# Ka coding rules

Read `context/index.md` first, then only the files it points to for your task.
Never load any `*.interview.md` file (keeps context lean).

## Commands
- `uv sync` install
- `uv run pytest` tests
- `uv run ruff check .` lint
- `uv run ka check|import|statements` CLI
- `uv run ka google login|status|probe`, `uv run ka sheet push` (flag `google`)
- `uv run ka suggest` queue category suggestions for uncategorised rows (flag `category_suggestions`)
- `uv run ka intake FILE... [--memory F --source NAME]...` resume and memory exports to pending cards (flag `intake`); `uv run ka serve` web UI on 127.0.0.1:8000 (flag `web_ui`); `cd ui && npm install`, `npm run dev` (proxy to :8000), `npx vitest run`, `npm run build`

## Ka rules
- No LLM call in the parser or tagging path.
- Money is `Decimal`, never `float`. Stored amounts are signed (negative = money out).
- Before editing, list the files and callers affected.
- No personal data, real statements, `.env` or secrets in this repo. The commit hook (`scripts/commit_guard.py`) enforces it; never edit the denylist to get past it.
- Personal data lives in the private data repo at the path in `config.yaml`.

## Structure
- Organise by feature, same name everywhere: `server/api/<feature>.py` maps to `context/flows/<feature>`.
- Core logic: `server/agent`, `server/finance`, `server/memory`, `server/integrations`, `server/store`. Tests mirror `server/`.

## Feature flags
- Every in-progress feature goes behind a flag in `config.yaml`, default off. Remove the flag when stable.

## Docs
- When a flow changes, update its `context/flows/` doc in the same commit (use the `flow-docs` skill).
- Tests: keep them few. One test per risky behaviour (money, parsing, guard, store), not per function.
