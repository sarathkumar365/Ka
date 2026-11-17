# Flow: pending (UI)

**Summary.** The Pending screen lists queued memories and onboarding intake cards (by-job cards with a tickbox per line, see [intake.md](intake.md)) and finance rule suggestions (bundle cards with section `categories` or `types`, see [import-statement.md](import-statement.md)) and statement import cards from the Drive inbox (see [google.md](google.md)) from `GET /api/pending` and approves or rejects them through the same functions as `ka pending`. Approval writes a validated git commit to the data repo; both actions add an activity row.

## Worked example

A queued item replaces memory M-0001. The card shows "Saved now" (the old text, struck through) next to "Would become". Approve calls `approve_pending`; if the old memory is no longer active the call fails with 409 and the card shows the message and refreshes the list.

## Why this way

- **One code path.** The UI calls `server/memory/pending.py`, so CLI and UI cannot disagree about duplicates or replaced entries.
- **Optimistic nothing.** The card leaves only after the server answers; a failure is visible next to the item.

## Failure cases

| Case | Result |
|---|---|
| Item already handled in the CLI | 409, card shows the message, list refreshes |
| Data repo has uncommitted edits to `memory.yaml` | 409 with the writer's message |
| Categories card approved | Rules committed, then empty categories on stored rows filled; result says `categorised N rows` |

Source: `server/api/pending.py`, `ui/src/features/pending/*`. Terminal flow: [review-pending.md](review-pending.md)

Interview questions: [pending.interview.md](pending.interview.md)
