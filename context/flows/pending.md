# Flow: pending (UI)

**Summary.** The Pending screen lists queued memories and onboarding intake cards (by-job cards with a tickbox per line, see [intake.md](intake.md)) and finance rule suggestions (bundle cards with section `categories` or `types`, see [import-statement.md](import-statement.md)) and statement import cards from the Drive inbox (see [google.md](google.md)) from `GET /api/pending` and approves or rejects them through the same functions as `ka pending`. Approval writes a validated git commit to the data repo; both actions add an activity row.

## Worked example

The screen shows one card at a time, as in the design: all cards sit in one grid cell, the first is current and the rest wait hidden below it; the subtitle says "2 of 5. Ka inferred these and needs a yes or no." A queued item replaces memory M-0001, so the card shows "Saved now" next to "Would become". Approve calls `approve_pending`; on success the card slides out to the right (left for Reject) while the next one rises into place, and its id stays out of the queue even if the list refetch is slow, so a decided card never comes back. If the old memory is no longer active the call fails with 409; the card stays and shows the message. With nothing left the screen says "Nothing is waiting for you." with a check.

## Why this way

- **One code path.** The UI calls `server/memory/pending.py`, so CLI and UI cannot disagree about duplicates or replaced entries.
- **Optimistic nothing.** The card leaves only after the server answers; a failure is visible next to the item.
- **One card at a time.** A decision per card, as the design asks, keeps the owner on one question; a bundle that needs another card first (a job before its domains) simply waits behind it.

## Failure cases

| Case | Result |
|---|---|
| Item already handled in the CLI | 409, card shows the message, list refreshes |
| Data repo has uncommitted edits to `memory.yaml` | 409 with the writer's message |
| Categories card approved | Rules committed, then empty categories on stored rows filled; result says `categorised N rows` |

Source: `server/api/pending.py`, `ui/src/features/pending/*`. Terminal flow: [review-pending.md](review-pending.md)

Interview questions: [pending.interview.md](interview/pending.interview.md)
