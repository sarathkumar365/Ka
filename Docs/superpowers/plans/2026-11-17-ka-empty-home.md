# Empty Home Opens Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Ka knows nothing about the owner, the app opens on Onboarding and the chat home points there; the hard-coded suggestion pills are gone.

**Architecture:** `GET /api/onboarding/status` stops trusting the one-time `onboarding_done` flag and decides from the data itself: no profile data and no cards waiting in Pending means onboarding is needed. The UI already redirects once per page load on `needed`; the chat empty state reads the same status to show a "Set up Ka" call to action instead of pills.

**Tech Stack:** FastAPI, SQLite (`Db`), React 19, TanStack Query, Vitest, pytest.

**Spec:** the owner's request (2026-11-17): "Remove those pills… we will add it later [from] learned user config… if there is no profile or no data… onboard screen should be coming by default." Setup link "is fine, but still improve it."

## Global Constraints

- Pills removed outright. No replacement suggestion source in this plan (learned suggestions are a later feature).
- "No data" = profile name empty AND no education entries AND no jobs AND no memory entries. Finance data does not count (a statement import does not tell Ka who the owner is).
- Flag `intake` off still means never redirect.
- Unreadable data repo still means never redirect (`reason: "unavailable"`).
- The redirect stays once per page load (`useFirstRunRedirect`), so Skip and links keep working.

## Review Focus

- Owner sent onboarding but has not approved the cards yet, then reloads: must land on chat, not Onboarding again (cards waiting = not needed). Test in Task 1.
- Owner rejects every card, data still empty: next load opens Onboarding again. This is intended; test in Task 1.
- Owner clicks Skip with no data: lands on chat, sees the "Set up Ka" card, no redirect loop within that page load (existing gate test covers once-per-load).
- Status request fails or is loading: chat empty state shows the neutral line, never a flash of the setup card. Test in Task 2.
- Profile has only a name typed in Basics and approved: counts as data, no redirect. Test in Task 1.

---

### Task 1: Status decides from data, not a done flag

**Files:**
- Modify: `server/api/onboarding.py`
- Modify: `ui/src/lib/api.ts:138` (remove `completeOnboarding`)
- Modify: `ui/src/features/onboarding/OnboardingPage.tsx` (Skip and leave no longer call complete; on leave, `qc.invalidateQueries({ queryKey: keys.onboarding })`)
- Test: `tests/api/test_onboarding.py`
- Docs: `context/flows/intake.md` (first-run section), via the `flow-docs` skill

**Interfaces:**
- Produces: `GET /api/onboarding/status` → `{"needed": bool, "reason": "off" | "unavailable" | "has_data" | "pending" | "first_run"}`. `POST /api/onboarding/complete` and the `onboarding_done` state key are removed.

- [ ] **Step 1: Rewrite the tests**

Keep `test_first_run_when_flag_on_repo_empty_and_not_done` (rename `test_first_run_when_repo_empty`), `test_flag_off_never_needs_onboarding`, `test_existing_data_never_needs_onboarding`, `test_unreadable_repo_does_not_trap_the_owner`. Delete `test_complete_persists_and_status_flips`. Add, using the `empty_repo` fixture (also write `profile.yaml` with `name: ""`, empty `education.yaml` and `memory.yaml` there so the fixture is truly empty):

```python
def test_a_name_alone_counts_as_data(empty_repo):
    (empty_repo.data_repo / "profile.yaml").write_text('name: "Avery"\n')
    assert status(client_for(empty_repo)) == {"needed": False, "reason": "has_data"}

def test_cards_waiting_in_pending_hold_the_redirect(empty_repo):
    db = Db(empty_repo.db_path)
    # one open card of any kind, created the way tests/api/test_pending.py creates one
    ...
    assert status(client_for(empty_repo)) == {"needed": False, "reason": "pending"}

def test_empty_again_after_rejecting_everything_needs_onboarding(empty_repo):
    # create one card, reject it through POST /api/pending/{id}/reject
    assert status(c) == {"needed": True, "reason": "first_run"}

def test_complete_endpoint_is_gone(empty_repo):
    assert client_for(empty_repo).post("/api/onboarding/complete").status_code in (404, 405)
```

- [ ] **Step 2: Run, expect failures**

Run: `uv run pytest tests/api/test_onboarding.py -q`
Expected: the name, pending and gone tests FAIL.

- [ ] **Step 3: Implement in `server/api/onboarding.py`**

Order of checks: flag off → `off`; `load_data` raises → `unavailable`; any of `profile.name.strip()`, `education.entries`, `jobs.jobs`, the memory file's entries → `has_data`; any open pending card (use the same `Db` listing `server/api/pending.py` uses) → `pending`; else `first_run`. Delete `DONE`, `complete`, and the `onboarding_done` read. Remove `completeOnboarding` from `api.ts` and its use in `OnboardingPage.tsx`.

- [ ] **Step 4: Run backend and UI tests**

Run: `uv run pytest -q && uv run ruff check . && (cd ui && npx vitest run && npx tsc -b)`
Expected: all pass, no type errors.

- [ ] **Step 5: Update `context/flows/intake.md`** first-run part: status is data-based; cards waiting hold the redirect; no done flag.

- [ ] **Step 6: Stage** (commit only after the owner says yes).

---

### Task 2: Chat home without pills, with a setup card when empty

**Files:**
- Modify: `ui/src/features/chat/ChatPage.tsx:14,131-146`
- Modify: `ui/src/styles.css:110` (delete `.chip`; nothing else uses it)
- Create: `ui/src/features/chat/emptyState.ts`
- Test: `ui/src/features/chat/emptyState.test.ts`

**Interfaces:**
- Consumes: `OnboardingStatus` from Task 1 via `useQuery({ queryKey: keys.onboarding, queryFn: api.onboardingStatus })` (same key the Shell uses, so no extra request).
- Produces: `emptyState(status: OnboardingStatus | undefined): 'setup' | 'ask'`.

- [ ] **Step 1: Write the failing test**

```ts
test('setup card only when the server says onboarding is needed', () => {
  expect(emptyState(undefined)).toBe('ask') // loading or failed: no flash
  expect(emptyState({ needed: false, reason: 'has_data' })).toBe('ask')
  expect(emptyState({ needed: false, reason: 'pending' })).toBe('ask')
  expect(emptyState({ needed: true, reason: 'first_run' })).toBe('setup')
})
```

- [ ] **Step 2: Run, expect FAIL** — `cd ui && npx vitest run src/features/chat/emptyState.test.ts` → "emptyState is not defined".

- [ ] **Step 3: Implement**

`emptyState` returns `status?.needed ? 'setup' : 'ask'`. In `ChatPage.tsx` delete `PROMPTS` and the chip row, drop the `settings.flags.intake` link. Empty state:
- `ask`: the existing line "Ask about your profile, your career or your money."
- `setup`: lead "Ka doesn't know you yet.", sub "Add your basics, a resume and what other assistants know about you. Ka reads it once and you approve what it keeps.", and a `button.primary` "Set up Ka" that navigates to `/onboarding`. The composer stays usable below.

Remove `settings` from `ChatPage` if nothing else in the file reads it.

- [ ] **Step 4: Run** `cd ui && npx vitest run && npx tsc -b && npm run build` → all pass.

- [ ] **Step 5: Look at it.** Build, serve against a scratch `KA_CONFIG` with an empty data copy, open `/chat` at desktop and 390 px: setup card centred, no pills, no horizontal scroll; open `/` fresh: lands on `/onboarding`. With a name in `profile.yaml`: `/chat` shows the plain line.

- [ ] **Step 6: Stage** (commit only after the owner says yes).
