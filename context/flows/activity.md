# Flow: activity

**Summary.** Every tool call in a web chat and every pending approval or rejection writes one sentence to the `activity` table. `GET /api/activity` returns them newest first; the screen groups them by day.

## Worked example

`search_transactions` returns 12 rows: `describe_call` produces "Searched transactions, 12 rows." with kind `read`. A declined `propose_change` produces "Proposed a change to your data. You declined it." with kind `change`.

## Why this way

- **Sentences, not raw calls.** `describe_call` never includes argument values, so the log cannot leak amounts or merchant names that were only search terms.
- **Written by the API layer.** The loop stays free of web concerns. Cost: terminal chats are not in the log.

## Failure cases

| Case | Result |
|---|---|
| Unknown tool name | "Used <name>." |
| Provider error | an `error` row with the readable message |

Source: `server/api/{activity,describe}.py`, `server/store/db.py`, `ui/src/features/activity/*`

Interview questions: [activity.interview.md](activity.interview.md)
