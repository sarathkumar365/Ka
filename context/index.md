# Context index

| File | Covers |
|---|---|
| `decisions.md` | Why each choice was made: redacted design spec plus step 1-3 addendum |
| `conventions.md` | Code style, testing, naming |
| `flows/` | One doc per core flow (see below) |

## Flows

| Flow | Doc | Source files |
|---|---|---|
| import-statement | `flows/import-statement.md` | `server/finance/{parser,reconcile,tagging,store,importer}.py`, `server/cli.py` |
| tools | `flows/tools.md` | `server/agent/tools/*.py`, `server/finance/{queries,statements}.py`, `server/integrations/data_repo/writer.py` |
| ask-question | `flows/ask-question.md` | `server/agent/{loop,prompt}.py`, `server/agent/adapters/*.py`, `server/store/db.py`, `server/chat.py` |
| nightly-extraction | `flows/nightly-extraction.md` | `server/memory/extract.py`, `server/cli.py` |
| review-pending | `flows/review-pending.md` | `server/memory/pending.py`, `server/agent/tools/memory_tools.py`, `server/cli.py` |
| evals | `flows/evals.md` | `tests/evals/*` |
