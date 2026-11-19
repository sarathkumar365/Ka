# Context index

| File | Covers |
|---|---|
| `decisions.md` | Why each choice was made: redacted design spec plus dated addenda (steps 1-3, UI, intake, first-run, Google, categories, private routing, send-once) |
| `conventions.md` | Code style, testing, naming |
| `flows/` | One doc per core flow (see below) |

## Flows

| Flow | Doc | Source files |
|---|---|---|
| import-statement | `flows/import-statement.md` | `server/finance/{parser,reconcile,tagging,store,importer,suggest}.py`, `server/cli.py` |
| tools | `flows/tools.md` | `server/agent/tools/*.py`, `server/finance/{queries,statements}.py`, `server/integrations/data_repo/writer.py` |
| ask-question | `flows/ask-question.md` | `server/agent/{loop,prompt}.py`, `server/agent/prompt.md`, `server/agent/adapters/*.py`, `server/store/db.py`, `server/chat.py` |
| nightly-extraction | `flows/nightly-extraction.md` | `server/memory/extract.py`, `server/scheduler.py`, `server/cli.py` |
| review-pending | `flows/review-pending.md` | `server/memory/pending.py`, `server/agent/tools/memory_tools.py`, `server/cli.py` |
| evals | `flows/evals.md` | `tests/evals/*` |
| chat | `flows/chat.md` | `server/api/{chat,approvals,describe,conversations}.py`, `server/agent/loop.py`, `server/agent/adapters/chain.py`, `ui/src/features/chat/*`, `ui/src/app/Sidebar.tsx`, `ui/src/lib/stream.ts` |
| pending (UI) | `flows/pending.md` | `server/api/pending.py`, `ui/src/features/pending/*` |
| google | `flows/google.md` | `server/integrations/google/*`, `server/finance/{drive_inbox,sheet_copy}.py`, `server/api/google.py`, `ui/src/features/settings/GoogleSection.tsx`, `ui/src/features/pending/StatementCard.tsx` |
| activity | `flows/activity.md` | `server/api/{activity,describe}.py`, `ui/src/features/activity/*` |
| settings | `flows/settings.md` | `server/api/settings.py`, `ui/src/features/settings/*`, `ui/src/lib/theme.ts` |
| pwa | `flows/pwa.md` | `ui/vite.config.ts`, `ui/index.html`, `server/api/app.py`, `ui/src/main.tsx`, `ui/scripts/make-icons.mjs`, `scripts/setup.sh` |
| intake | `flows/intake.md` | `server/intake/*`, `server/api/{intake,onboarding}.py`, `ui/src/features/onboarding/*`, `ui/src/app/Shell.tsx` |
| data repo | `flows/data-repo.md` | `server/integrations/data_repo/{loader,writer}.py`, `server/integrations/data_repo/schemas/*` |
| config | `flows/config.md` | `server/config.py`, `server/env.py`, `config.example.yaml` |
| commit guard | `flows/commit-guard.md` | `scripts/commit_guard.py`, `scripts/hooks/pre-commit` |
