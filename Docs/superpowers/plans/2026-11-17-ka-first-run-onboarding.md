# Ka First-Run Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the app is opened with no career data and onboarding never finished or skipped, it starts on the Onboarding screen, and it never forces it again once the owner has finished, skipped, or has data.

**Architecture:** A tiny `app_state` key/value table in SQLite stores `onboarding_done`. `GET /api/onboarding/status` decides `needed` on the server (flag on, not done, no jobs stored); `POST /api/onboarding/complete` records the choice. The UI shell asks for the status on load and redirects to `/onboarding` while `needed` is true. Every Onboarding screen has "Skip for now", so the owner is never trapped.

**Tech Stack:** FastAPI, SQLite (existing `Db`), React Router and TanStack Query, vitest.

**Spec:** the owner's request (first-run should open on onboarding, like normal apps) plus `Docs/superpowers/specs/2026-11-17-onboarding-intake-design.md` for the screen. No separate design doc; the calls are listed under Global Constraints.

## Global Constraints

- "Needs onboarding" means all three: `flags.intake` is true, `onboarding_done` is not set, and `data.jobs.jobs` is empty. Any other state never redirects.
- A failure to decide (data repo unreadable, status request failing) must never redirect or block: the owner reaches the app.
- The redirect applies to every route except `/onboarding` itself. A deep link such as `/chat/C-1` is redirected too; after Skip or Done the owner lands on `/chat` (Done goes to `/pending`, where the cards are).
- "Skip for now" and finishing both set `onboarding_done`. "Go through setup again" in Settings stays a plain link and does not clear the flag.
- No change to the agent loop, tools or the data repo. State lives in `ka.db`, not in the YAML files.
- No new feature flag: this rides on the existing `intake` flag, default off, so the redirect never appears until intake is on.
- Public repo: no personal data in code or tests. Tests minimal: one per risky behaviour.
- Commits: commit guard hook; touch `.claude/.reviewed` only after the owner says yes; no `Co-Authored-By` or Claude trailers; noreply author.

## Review Focus

1. Status request fails or the data repo cannot be read → no redirect, the app opens normally (T1 and T2 tests).
2. Owner skips → never sent back, also after a reload and a restart (T1 test on persistence; T2 gate test).
3. Existing owner who already has jobs stored but never did onboarding → no redirect (T1 test).
4. Redirect loop: already on `/onboarding` → no redirect (T2 test).
5. Intake flag off → no redirect even on an empty repo (T1 test).

---

### Task 1: Onboarding state and status API

**Files:**
- Modify: `server/store/db.py`, `server/api/app.py`
- Create: `server/api/onboarding.py`
- Test: `tests/store/test_db.py`, `tests/api/test_onboarding.py`

**Interfaces:**
- Consumes: `Db`, `load_data(root) -> KaData` (`data.jobs.jobs`), `get_cfg`, `get_db`, the `intake` flag in `cfg.flags`.
- Produces:
  - `Db.get_state(key: str) -> str | None` and `Db.set_state(key: str, value: str) -> None` over a new table `app_state(key text primary key, value text not null)` created in `SCHEMA`.
  - `GET /api/onboarding/status` → `{"needed": bool, "reason": "first_run" | "done" | "has_data" | "off" | "unavailable"}`. Order of checks: flag off → `off`; `onboarding_done` set → `done`; any stored job → `has_data`; data repo unreadable → `unavailable` (needed false); else `first_run` (needed true).
  - `POST /api/onboarding/complete` → `{"ok": true}`; sets `onboarding_done` to `"1"`; idempotent.

- [ ] **Step 1: Write the failing tests.** `tests/store/test_db.py::test_app_state_roundtrip` (missing key is None; set then get; set again overwrites). `tests/api/test_onboarding.py` (TestClient; the fixture repo has jobs, so tests that need an empty repo write `domains: []\njobs: []\n` to `jobs.yaml` first; use a config copy with `flags={"intake": True}` like `tests/api/test_intake.py`): `test_first_run_when_flag_on_repo_empty_and_not_done` → `{"needed": True, "reason": "first_run"}`; `test_flag_off_never_needs_onboarding` (Review Focus 5); `test_existing_data_never_needs_onboarding` (fixture jobs present → `has_data`, Review Focus 3); `test_complete_persists_and_status_flips` (POST complete, status is `done`, and a second client built on the same config still says `done`, Review Focus 2); `test_unreadable_repo_does_not_trap_the_owner` (delete `profile.yaml` so `load_data` fails → needed false, reason `unavailable`, Review Focus 1).
- [ ] **Step 2: Run** `uv run pytest tests/store/test_db.py tests/api/test_onboarding.py -q`. Expected: FAIL (missing names).
- [ ] **Step 3: Implement** the table and `Db` methods, then `server/api/onboarding.py` with both routes (catch `DataRepoError` and `OSError` around `load_data`), and include the router in `create_app`.
- [ ] **Step 4: Run** the same command and `uv run pytest -q` and `uv run ruff check .`. Expected: pass, clean.
- [ ] **Step 5: Commit** `feat: onboarding status and complete endpoints`.

### Task 2: Redirect on first run, Skip, and finish

**Files:**
- Create: `ui/src/features/onboarding/gate.ts`, `ui/src/features/onboarding/gate.test.ts`
- Modify: `ui/src/lib/api.ts`, `ui/src/app/Shell.tsx`, `ui/src/features/onboarding/OnboardingPage.tsx`
- Test: `ui/src/features/onboarding/gate.test.ts`

**Interfaces:**
- Consumes: Task 1 routes.
- Produces: in `api.ts`: `type OnboardingStatus = { needed: boolean; reason: string }`, `api.onboardingStatus(): Promise<OnboardingStatus>`, `api.completeOnboarding(): Promise<{ ok: boolean }>`, query key `keys.onboarding`. In `gate.ts`: `shouldRedirect(status: OnboardingStatus | undefined, pathname: string): boolean`, true only when `status?.needed === true` and `pathname` does not start with `/onboarding`.

- [ ] **Step 1: Write the failing test** `gate.test.ts`: `shouldRedirect` is false for `undefined` (request failed or still loading), for `{needed: false}`, and for `{needed: true}` on `/onboarding` and `/onboarding/anything`; true for `{needed: true}` on `/chat`, `/chat/C-1` and `/pending`.
- [ ] **Step 2: Run** `cd ui && npx vitest run src/features/onboarding`. Expected: FAIL.
- [ ] **Step 3: Implement.** `gate.ts` as specified. `Shell.tsx`: `useQuery({ queryKey: keys.onboarding, queryFn: api.onboardingStatus, retry: false, refetchOnWindowFocus: false })`; an effect calls `nav('/onboarding', { replace: true })` when `shouldRedirect(data, pathname)`. `OnboardingPage.tsx`: add a "Skip for now" text button on every step that runs a mutation `api.completeOnboarding()` then sets the cached status to `{needed: false, reason: "done"}` and navigates to `/chat`; the last step's Done does the same completion and navigates to `/pending`.
- [ ] **Step 4: Run** `npx vitest run`, `npx tsc -b`, `npm run build`. Expected: pass, no errors. Then in the browser pane against a scratch copy of the data repo with the intake flag on and an empty `jobs.yaml` (`KA_CONFIG` pointing at it, as in the intake plan): opening `/chat` lands on `/onboarding`; Skip goes to `/chat`; reloading stays on `/chat`; `/onboarding` stays reachable from Settings. Also stop the server mid-way and reload to confirm the app does not redirect when the status request fails. Expected: all true.
- [ ] **Step 5: Commit** `feat: open on onboarding on first run, with skip`.

### Task 3: Docs and final checks

**Files:**
- Modify: `context/flows/intake.md`, `context/decisions.md`

- [ ] **Step 1:** Add a "First run" section to `context/flows/intake.md` (the three conditions, where the flag is stored, Skip, failure behaviour, source files `server/api/onboarding.py` and `ui/src/features/onboarding/gate.ts`) using the `flow-docs` skill, and a short addendum to `context/decisions.md`.
- [ ] **Step 2: Run** `uv run pytest -q`, `uv run ruff check .`, `cd ui && npx vitest run && npx tsc -b && npm run build`, `uv run python scripts/commit_guard.py`. Expected: all pass, guard exit 0.
- [ ] **Step 3: Commit** `docs: first-run onboarding flow`.

---

## Self-review

- **Coverage:** open on onboarding when there is no data and it was never done → T1 status plus T2 redirect; never trapped → Skip and failure-safe status; deep links → shell-level redirect. The wipe the owner asked for was done outside the plan (chats, pending, activity and jobs in `ka.db`; finance rows and data files untouched; backup at `ka-data/local/ka.db.bak-before-wipe`).
- **Types:** the status JSON in T1 matches `OnboardingStatus` in T2; the `reason` values are the same set.
- **Open for the executor:** exact copy of the Skip button; whether the status query should refetch after intake approves the first job (the server already flips to `has_data`, so a refetch on navigation is enough).
