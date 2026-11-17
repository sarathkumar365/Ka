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
