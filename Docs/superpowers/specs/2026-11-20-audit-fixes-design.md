# Audit fixes: phone UI, security and stability, docs

Date: 2026-11-20. Status: draft for the owner's approval.

## Why

A fresh audit after the multi-account change found three kinds of problems:

1. The phone layout breaks in daily use. The worst case is the chat input on an iPhone: the text and send button float above the box.
2. There are security and stability gaps that matter now that sign-up is open.
3. Docs no longer match the code.

The owner wants every page and every input to work on current iPhones (iOS 15 Pro to 17 Pro sizes, portrait and landscape, installed as a PWA). Breakage like the chat input "should never happen". Scrolling must be smooth, and the main chat must not show a scrollbar.

## Goals

- Every page and every input works on iPhone sizes from 375x667 to 430x932, plus landscape, with the home-bar safe area applied. My call: the SE size (375x667) is in scope, as the smallest phone still sold.
- Chat input, typing state, thinking ring, search bar and waiting dot all line up with the input box in every state.
- Close the security and stability gaps listed in Batch 2.
- Docs describe what the code does.

## Non-goals

- No redesign. Keep the existing look, the Ka entity and its animations, colours and spacing scale.
- No new features.
- Desktop layout must not change apart from the scrollbar and scroll behaviour.

## Anti-goals (a failure even if it "works")

- A fix that lines things up only at one screen size, or only when the safe area is zero.
- Losing any chat animation or making it jerky.
- New approval prompts on everyday chats that never touched outside content.

## Approaches considered

- **Three batches, phone UI first (chosen by the owner).** UI, then security and stability, then docs. Each batch gets its own tests and its own commit, so the visible breakage is fixed first and each batch can be reviewed apart.
- **One pass for everything.** Fewer round trips, but one large diff mixing CSS, auth and docs. That makes review harder and delays the fix the owner sees every day.

## Batch 1: phone UI

### Root cause of the broken chat input

The composer sits `calc(24px + env(safe-area-inset-bottom))` above the bottom (`ui/src/styles.css:136`). Everything drawn over it uses fixed offsets that ignore the safe area, so on an iPhone with a home bar (34px) each of these lands 34px too low:

- the typing box, `bar` in `ui/src/features/chat/entityStyle.ts:39`
- the docked dot, thinking, searching and waiting positions in `entityStyle.ts:40-67`
- the thinking ring, `.thinking-ring` top in `styles.css:154`

The message list stops 96px from the bottom (`styles.css:92`), but the composer's top is 114px up, so the last line hides behind it.

### Required behaviour

1. One shared CSS value for the bottom safe area, for example `--safe-b: env(safe-area-inset-bottom, 0px)` on `:root`. Every bottom-anchored chat element uses it: composer, message list bottom inset, entity typing box, docked dot, thinking, searching, waiting, thinking ring. With any safe area, the entity box and the composer have the same top and bottom (within 1px) in typing mode. The ring, dot and search bar sit inside the composer box in their modes.
2. iOS keyboard: when the composer or any input is focused, it stays fully visible above the keyboard. After the keyboard closes, no offset is left behind. The page is back at its resting position and nothing is shifted.
3. Landscape and short screens: drop `min-height: 560px` on `.app`. At 852x393 the header, the content and the composer all fit, and the empty-state text never overlaps the composer. Hide secondary text on short heights, as `.empty .sub` already does.
4. Form controls: add `-webkit-appearance: none` (and `appearance: none`) to text inputs, selects and textareas. Selects get a drawn chevron and the same height, padding and radius as inputs. Checkboxes keep their native look.
5. Onboarding:
   - Hidden steps must not add to the scroll height.
   - Changing step scrolls to the top of the step.
   - Step 5 entries must not use the page-column class `col` (`StepMemory.tsx:24`). They line up with the rest of the step at full width.
6. Page bottoms: `.page` bottom padding includes the safe area, so the last row (Sign out and others) clears the home bar. The same applies to any other scrolling screen.
7. Scrolling:
   - Hide the scrollbar in the main chat (`.msgs`). Other pages keep normal scrolling, and their scrollbar may stay (my call: hide it there too on touch devices only).
   - New messages scroll smoothly. The chat follows the stream only while the reader is at or near the bottom (within about 80px); if they scrolled up to read, it does not pull them down.
   - Set `overscroll-behavior` so the whole app does not bounce. Inner lists still scroll with momentum.
8. The onboarding ring canvas uses the dynamic viewport (`inset: 0` with no `100vh`, or `100dvh`), so it lines up on iOS Safari.
9. Copy: the send step names the provider in plain words (e.g. "OpenAI", not "openai").

### Verification

- Unit tests where logic exists: the "follow only when near the bottom" rule and any new entity geometry helper.
- Browser check at 375x667, 393x852, 430x932 and 852x393, with the safe area simulated at 34px bottom and 59px top. Check every page: welcome, sign-up, login, onboarding steps 2-6, chat (empty, typing, thinking, searching, answering, waiting, docked with a long thread), pending, loops, activity, settings, chats sidebar.
- iOS Simulator (iPhone 17 Pro, and a small one such as iPhone SE) in Safari for keyboard behaviour, native control styling and the real safe area.

## Batch 2: security and stability

Each item gets one test for the risky behaviour.

1. **Login lockout.** Remove the hard per-username block (`per_user`, `server/api/auth.py:31`). Keep the per address+username failure limit and the per-address login limit. My call: no slowdown replacement, because Ka sits on a tailnet.
2. **Client address.** Make uvicorn's proxy handling explicit (`proxy_headers`, `forwarded_allow_ips` in `server/cli.py`) so only one layer reads `X-Forwarded-For`. Document what tailscale serve sends once it has been checked on the real machine.
3. **Outbound data after outside content.** Once a conversation has read untrusted content (web results, fetched pages, statement or movie text), `fetch_page` may only open URLs that appeared in earlier results or in the person's own messages. Any other URL needs approval.
   - My call: this conversation-long allowlist is the only new rule. The existing "block risky tools while untrusted" rule (`server/agent/loop.py:123`) keeps its per-turn scope, so finance chats get no new prompts.
4. **`remember`.** Save without asking only when the person's message is a clear request ("remember that ..." or "remember: ..."). Otherwise ask for approval.
5. **Private chats and tracing.** Do not export message input or output to Langfuse for private conversations, so only timings and counts leave.
   - My call: check `db.is_private` when each span is exported, not when it starts. A chat turns private in the turn where finance data first appears, so that turn is covered too. Earlier turns held no finance data.
6. **Page fetch limits.** Stream the body, stop at the byte cap, and enforce an overall deadline. Pin the checked IP for the connection (or check the connected peer) to block DNS rebinding.
7. **Fair sharing between accounts.**
   - At most 10 active loops per account.
   - One loop run at a time per account, on its own executor, apart from system jobs.
   - At most 2 chat turns running at once per account.
   - `POST /loops/{id}/run` hands off and returns 202 with the run id. The Loops screen shows the run as running and refreshes the existing runs list until it ends.
   - My call: over a limit, refuse rather than queue. A third chat turn gets 429 "Another chat is still answering. Try again in a moment.", shown in the composer like other errors. A manual run while one is running gets 409 "This loop is already running." A new loop past 10 gets 409 "You have 10 active loops. Pause one first."
8. **Headless loops.** Hide `schedule_task` and `remember` from loop runs.
9. **Loop cost cap.** Pass the run's budgeted adapter to the page summariser so its calls count. Estimate cost from tokens when the provider returns none, using a small price table in config. My call: an unknown model counts at the most expensive listed price.
10. **Smaller fixes:**
    - Compare the full origin (scheme, host, port) in the cross-site write check.
    - Expire OAuth state entries after 10 minutes, at most 5 per account.
    - Sweep and cap rate-limiter keys.
    - Add security headers (`frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: same-origin`, a CSP that allows the app's own assets).
    - A bad `Content-Length` returns 400.
    - Revoke the old session cookie at login, and delete expired sessions on a schedule.
    - The watchdog alert key includes the last check-in, so it can fire again.
    - `finance_sum_transactions` counts unique ids.
    - Approving a loop card refuses if the new diff differs from the stored one.
    - Close httpx clients.
    - Return malformed tool-call arguments to the model as an error.

## Batch 3: docs

Fix the 15 mismatches from the audit:

1. Lockout wording in `context/decisions.md:394`, `context/flows/login.md:32` and the multi-account spec: make it match Batch 2.
2. `login.md`: add the per-address login limit (20 per 10 minutes, 429) to the failure table, and add `/auth/logout`.
3. `context/flows/pwa.md:18` "No auth": the tailnet limits who can reach Ka; accounts and sessions limit what each person sees; sign-up is open.
4. `context/index.md:21` names the deleted `server/agent/tools/memory_tools.py`; the real file is `server/toolkits/core/memory.py`.
5. `context/index.md` missing files:
   - loops row: `server/api/app.py`, `server/cli.py`
   - nightly-extraction and google rows: `server/jobs.py`, `server/api/app.py`
   - no row at all: `server/finance/models.py`, `ui/src/lib/api.ts`, `ui/src/lib/icons.tsx`, `ui/src/styles.css`
6. `review-pending.md:3,26`, `pending.md:20`, `tools.md:32`: flat `memory.yaml` becomes `memory/<toolkit>.yaml` (core is `memory/core.yaml`).
7. `Docs/post-build-setup.md:5`: step 1 (uncommitted on `next-phase`) is done; remove it.
8. `context/flows/settings.md`: add the "Pause all loops" switch, Sign out with the username, and the per-account Drive folder and Sheet id inputs.
9. Multi-account spec line 121 says nightly runs at 03:00; it runs hourly per account. Remove the unused `cron hour 3` trigger in `server/scheduler.py:106`.
10. AGENTS.md: add `uv run ka loops [list|pause|resume|run ID]` (flag `loops`) and `ka serve --port`.
11. `ka check` with several accounts and no `--user` prints ok and validates nothing. My call: make it validate every account, then update AGENTS.md:10, `login.md:44` and `data-repo.md:35` to match.
12. AGENTS.md:24-25: add `server/auth`, `server/loops`, `server/toolkits`, `server/web` to core logic; say `context/index.md` is the map from source to flow (several api files have no flow of the same name).
13. Route tables: `google.md` (`/google/status|login|callback|disconnect|sync|push|settings`) and `loops.md` (`PATCH`/`DELETE /loops/{id}`, `/loops/{id}/runs`, `/loops/{id}/run`, `PUT /loops/paused`).
14. Default data repo path: `config.example.yaml:1` and `post-build-setup.md:12` say `~/Projects/ka-data`, while `scripts/setup.sh:12` and `pwa.md:7` say `~/ka-data`. My call: `~/ka-data` everywhere, as the setup script already creates it.
15. "Owner" leftovers: `flags.md:33`, `data-repo.md:3`, `commit-guard.md:3` (the denylist is the operator's), `chat.md:21`, `intake.md:3,17,30,40`, `review-pending.md:7`: say "the person" or "the account". The multi-account spec says `WelcomePage` uses `KaRing`; it uses `Entity mode="empty"`.

Batch 1 and Batch 2 also update the flow docs for the flows they touch, in the same commit (`flow-docs` rule).

## Left to the builder

- The exact CSS mechanism for the keyboard (a `visualViewport` listener or CSS only), as long as Batch 1 item 2 holds in the Simulator.
- How short-height layouts hide secondary text.
- The price table values, and where the cost estimate lives.
- Test placement, following the existing test layout and the "few tests, risky behaviour only" rule.
