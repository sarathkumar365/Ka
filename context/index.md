# Context index

| File | Covers |
|---|---|
| `decisions.md` | Why each choice was made: redacted design spec plus step 1-3 addendum |
| `conventions.md` | Code style, testing, naming |
| `flows/` | One doc per core flow (see below) |

## Flows

| Flow | Doc | Source files |
|---|---|---|
| import-statement | `flows/import-statement.md` | `server/finance/{parser,reconcile,tagging,store,importer,suggest}.py`, `server/cli.py` |
| tools | `flows/tools.md` | `server/agent/tools/*.py`, `server/finance/{queries,statements}.py`, `server/integrations/data_repo/writer.py` |
| ask-question | `flows/ask-question.md` | `server/agent/{loop,prompt}.py`, `server/agent/adapters/*.py`, `server/store/db.py`, `server/chat.py` |
| nightly-extraction | `flows/nightly-extraction.md` | `server/memory/extract.py`, `server/scheduler.py`, `server/cli.py` |
| review-pending | `flows/review-pending.md` | `server/memory/pending.py`, `server/agent/tools/memory_tools.py`, `server/cli.py` |
| evals | `flows/evals.md` | `tests/evals/*` |
| chat | `flows/chat.md` | `server/api/{chat,approvals,describe}.py`, `server/agent/loop.py`, `server/agent/adapters/chain.py`, `ui/src/features/chat/*`, `ui/src/lib/stream.ts` |
| pending (UI) | `flows/pending.md` | `server/api/pending.py`, `ui/src/features/pending/*` |
| google | `flows/google.md` | `server/integrations/google/*`, `server/finance/{drive_inbox,sheet_copy}.py`, `server/api/google.py`, `ui/src/features/settings/GoogleSection.tsx`, `ui/src/features/pending/StatementCard.tsx` |
| activity | `flows/activity.md` | `server/api/{activity,describe}.py`, `ui/src/features/activity/*` |
| settings | `flows/settings.md` | `server/api/settings.py`, `ui/src/features/settings/*` |
| pwa | `flows/pwa.md` | `ui/vite.config.ts`, `ui/index.html`, `server/api/app.py` |
| intake | `flows/intake.md` | `server/intake/*`, `server/api/intake.py`, `ui/src/features/onboarding/*` |
