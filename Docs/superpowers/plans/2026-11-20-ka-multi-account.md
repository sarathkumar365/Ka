# Ka Multi-Account Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open sign-up for many fully isolated accounts, a home screen with Create account and Sign in, and every capability (data, search, approvals, Google, jobs, locks, UI caches) scoped per account.

**Architecture:** Accounts get opaque ids (`u_` + 12 hex) and a `users/<id>/` folder made from `server/users_starter/`. Every SQLite read and write is already scoped by `Db.user_id`; this plan closes the remaining gaps (ids, FTS, ownership checks), makes in-process state per account (approvals, Google auth, locks), runs background jobs once per account, and adds the signed-out UI routes. Legacy migration code is deleted, not adapted.

**Tech Stack:** Python 3.13, FastAPI, sqlite3/FTS5, APScheduler 3.11, git; React + TypeScript + Vite PWA, TanStack Query, vitest.

**Spec:** `Docs/superpowers/specs/2026-11-20-multi-account-design.md`

## Global Constraints

- Login always on, no flag. Sign-up open always.
- User id `u_` + `secrets.token_hex(6)`; username `^[a-z][a-z0-9_-]{2,31}$`, unique, lower case; password ≥ 10 characters.
- Sign-up limit: 5 per hour per client address. Login: 5 failures per (address, username) → that pair waits 15 minutes; 20 attempts per 10 minutes per address overall.
- Client address: `X-Forwarded-For` first entry only when `request.client.host` is `127.0.0.1` or `::1`; otherwise `request.client.host`.
- Login and sign-up never reveal whether a username exists, except sign-up's "that username is taken".
- No fallback to `config.yaml` for `drive_folder_id` / `sheet_id`; those keys are removed from `GoogleConfig`.
- Missing Drive folder message: `Your Google Drive folder is not set up yet. Add it in Settings to import statements.` Missing Sheet: `Your Google Sheet is not set up yet. Add it in Settings to keep a Sheet copy.`
- No per-account spending cap (owner's call).
- Money stays `Decimal`. No personal data in the code repo. Flow docs change in the same commit as the code (`flow-docs` skill). Tests: one per risky behaviour.
- Commits: the owner's noreply author, no Co-Authored-By trailer.

## Review Focus

1. Two accounts act at once (chat, approve a card, save a memory) → neither blocks, sees or commits the other's work. Pinned in Tasks 3, 4.
2. A request by account B naming account A's id (conversation, pending card, approval, intake job, loop task) → 404, never A's data. Pinned in Task 3.
3. Account B connects or disconnects Google while A is connected → A's token and status are untouched. Pinned in Task 5.
4. One account's background job throws → the other accounts' runs still happen. Pinned in Task 6.
5. Account A's session expires with an unsent message, then B signs in on the same phone → B never sees A's text or A's conversation URL. Pinned in Task 7.

---

### Task 1: Open sign-up with opaque account ids

**Files:**
- Modify: `server/auth/users.py` (drop `user_count` gate in `create_user`, opaque id, `username_taken`)
- Modify: `server/users.py` (add `start_user_space`, `user_id_for`; delete `claim_legacy_data`, `_legacy_files`, `_move_and_commit`, `_stamp_finance`, `only_user`; no Google fallback is Task 5)
- Modify: `server/store/migrations.py` (delete `backfill_user`)
- Modify: `server/store/db.py` (`user_id` required; `Db.system` passes a private flag; `LOCAL_USER` removed)
- Modify: `server/config.py` (`user_id` no longer read from YAML: `model_config` exclude or validator rejecting it)
- Modify: `server/api/auth.py` (`/auth/signup` replaces `/auth/setup`; status shape; sign-up limiter)
- Create: `server/locks.py` with `repo_lock` (Task 4 adds `user_lock` to it)
- Test: `tests/api/test_auth.py`, `tests/auth/test_auth.py`, `tests/test_users.py`, `tests/store/test_migrations.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `repo_lock(repo_root: Path) -> ContextManager` in `server/locks.py` — `fcntl.flock` on `repo_root/.ka.lock`.
- Produces: `create_user(db: Db, username: str, password: str, now: datetime) -> str` (returns `u_…` id; raises `AuthError("that username is taken")` on duplicate).
- Produces: `start_user_space(cfg: Config, user_id: str) -> Path` — copies `server/users_starter/` into `users/<id>/`, commits `data: start users/<id>` under `repo_lock(repo_root)`, raises `UserError` if the folder exists.
- Produces: `user_id_for(db: Db, username: str) -> str | None`.
- Produces: `GET /api/auth/status -> {"user": str|None, "username": str|None, "min_password": int, "username_rule": str}`; `POST /api/auth/signup {username, password} -> {"user": id}` (sets cookie).
- Produces: `Db(path, user_id: str, shared_threads=False, init_schema=True)`; `Db("x", "")` raises `ValueError("Db needs a user; use Db.system for auth")`.
- Produces: `app.state.on_user_created(user_id)` still called after sign-up (loops add built-ins).

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_auth.py
def test_anyone_can_sign_up_and_accounts_are_separate(empty_client):
    a = empty_client.post("/api/auth/signup", json={"username": "avery", "password": PW})
    assert a.status_code == 200 and a.json()["user"].startswith("u_")
    empty_client.cookies.clear()
    b = empty_client.post("/api/auth/signup", json={"username": "blake", "password": PW})
    assert b.status_code == 200 and b.json()["user"] != a.json()["user"]
    status = empty_client.get("/api/auth/status").json()
    assert (status["username"], status["min_password"]) == ("blake", 10)
    root = empty_client.app.state.cfg.data_repo
    assert (root / "users" / b.json()["user"] / "profile.yaml").is_file()

def test_taken_username_and_signup_limit(empty_client):
    empty_client.post("/api/auth/signup", json={"username": "avery", "password": PW})
    dup = empty_client.post("/api/auth/signup", json={"username": "avery", "password": PW})
    assert dup.status_code == 409 and dup.json()["detail"] == "that username is taken"
    codes = [empty_client.post("/api/auth/signup", json={"username": f"user{i}x", "password": PW}).status_code for i in range(6)]
    assert codes[-1] == 429
```

`empty_client` fixture (replaces `fresh`): an empty git data repo (only `.gitignore` with `local/\n.ka.lock\n`, one commit) and `create_app(Config(data_repo=root), …)`. Delete `tests/test_users.py` legacy-claim tests and `test_migrations` backfill test; keep `tests/auth/test_auth.py` tests for password checks, replacing "second account refused" with "duplicate username refused". `conftest.add_account` keeps writing `id=user, username=user`.

- [ ] **Step 2: Run tests, expect FAIL** — `uv run pytest tests/api/test_auth.py -q` → 404 on `/api/auth/signup`.
- [ ] **Step 3: Implement** the interfaces above. `signup` order: limiter (keyed on client address, `LoginLimiter(5, timedelta(hours=1))`) → `create_user` (422 on rule errors, 409 on taken) → `start_user_space` (on failure delete the users row and return 500 "could not create the account") → `on_user_created` → session cookie. Grep `Db(` call sites: all pass `cfg.user_id`; any that can see an empty one must fail loudly, which the new `ValueError` does.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `feat: open sign-up with opaque account ids`

### Task 2: Login protection per address and username

**Files:**
- Modify: `server/auth/ratelimit.py` (docstring; generic keyed limiter)
- Create: `server/auth/clientip.py`
- Modify: `server/auth/users.py` (`authenticate` drops the per-user DB lock; columns stay unused)
- Modify: `server/api/auth.py` (`login` uses two limiters)
- Test: `tests/auth/test_auth.py`

**Interfaces:**
- Produces: `client_ip(request) -> str` (rule in Global Constraints).
- Produces: `LoginLimiter.allow(key: str, now) -> bool`, `LoginLimiter.fail(key: str, now) -> None`, `LoginLimiter.blocked(key: str, now) -> bool` — `failures = LoginLimiter(5, timedelta(minutes=15))` keyed `f"{ip}|{username}"`, counted only on wrong password and cleared on success; `attempts = LoginLimiter(20, timedelta(minutes=10))` keyed on ip.

- [ ] **Step 1: Failing test**

```python
def test_lockout_is_per_address_not_per_account(make_client):
    c = make_client(login=False)
    bad = {"username": "avery", "password": "wrong password 1"}
    for _ in range(5):
        c.post("/api/auth/login", json=bad, headers={"x-forwarded-for": "10.0.0.9"})
    locked = c.post("/api/auth/login", json={"username": "avery", "password": PW}, headers={"x-forwarded-for": "10.0.0.9"})
    assert locked.status_code == 429
    other = c.post("/api/auth/login", json={"username": "avery", "password": PW}, headers={"x-forwarded-for": "10.0.0.7"})
    assert other.status_code == 200
```

(The TestClient's client host is `testclient`; make `client_ip` treat `testclient` like loopback only under tests by having the fixture set `app.state.trusted_proxies = {"testclient"}`; default `{"127.0.0.1", "::1"}`.)

- [ ] **Step 2: Run, expect FAIL** (second login 401 or 200 for the locked pair).
- [ ] **Step 3: Implement.** Locked pair answers 429 `too many attempts, try again later`.
- [ ] **Step 4: Run** `uv run pytest tests/auth tests/api/test_auth.py -q` → pass.
- [ ] **Step 5: Commit** `fix: login limits per address and username`

### Task 3: SQLite isolation gaps

**Files:**
- Modify: `server/store/db.py:88,257` and `server/loops/tasks.py:80` (`token_hex(8)`)
- Modify: `server/store/migrations.py` (add `_m3_fts_user`; `STEPS` gets it)
- Modify: `server/store/db.py` (`add_message` ownership, FTS insert with `user_id`, `search` filter on `f.user_id`, `list_conversations` subqueries add `m.user_id=c.user_id`)
- Test: `tests/store/test_db.py`

**Interfaces:**
- Produces: `_m3_fts_user(conn)` drops `message_fts`, recreates it as `fts5(text, conversation_id unindexed, message_id unindexed, role unindexed, at unindexed, user_id unindexed)`, refills from `messages` joined to `conversations` for user/assistant rows with string content.
- Produces: `Db.add_message` raises `KeyError("no such conversation")` when `conv_id` is not this user's.

- [ ] **Step 1: Failing test**

```python
def test_two_accounts_never_see_each_other(tmp_path):
    path = tmp_path / "ka.db"
    a, b = Db(path, "u_a"), Db(path, "u_b")
    ca = a.new_conversation(datetime(2026, 11, 20))
    a.add_message(ca, {"role": "user", "content": "secret pancakes"}, datetime(2026, 11, 20))
    a.add_pending("memory", {"text": "x"}, "chat", datetime(2026, 11, 20))
    assert b.search("pancakes") == [] and b.list_conversations() == [] and b.list_pending() == []
    assert b.messages(ca) == [] and not b.conversation_exists(ca)
    with pytest.raises(KeyError):
        b.add_message(ca, {"role": "user", "content": "hi"}, datetime(2026, 11, 20))
    assert len(ca.rsplit("-", 1)[1]) == 16
```

- [ ] **Step 2: Run, expect FAIL** (`add_message` accepts B; id suffix 4).
- [ ] **Step 3: Implement** as in Interfaces. API routes already 404 on foreign ids via `conversation_exists`/`get_pending`; add one API assertion: `GET /api/conversations/<A's id>` as B → 404 (in `tests/api/test_conversations.py` if it exists, else this test file via `make_client`).
- [ ] **Step 4: Run** `uv run pytest tests/store tests/api -q` → pass.
- [ ] **Step 5: Commit** `fix: close cross-account gaps in ids, search and messages`

### Task 4: Per-account server state and one git lock

**Files:**
- Modify: `server/locks.py` (add `user_lock`)
- Modify: `server/api/approvals.py`, `server/api/chat.py:70-80,154-158`
- Modify: `server/api/intake.py:53`, `server/api/pending.py:106,152`, `server/api/app.py:103-104`
- Modify: `server/finance/drive_inbox.py:24,61`, `server/finance/sheet_copy.py:18,51`
- Modify: `server/integrations/data_repo/writer.py:249` (use Task 1's `repo_lock` at the repo root)
- Test: `tests/api/test_chat.py` (approval), `tests/test_locks.py`

**Interfaces:**
- Produces: `user_lock(name: str, user_id: str) -> threading.Lock` (one lock per `(name, user_id)`, created on first use under a module lock).
- Consumes: Task 1 `repo_lock`; in `apply_change` the root passed is `git rev-parse --show-toplevel` of the folder passed to `apply_change`. `rev-parse HEAD` stays inside the lock (correct once every commit takes it).
- Produces: `ApprovalBroker.request(user_id: str) -> str`; `resolve(approval_id, approve, user_id: str | None = None) -> bool` (None = internal cancel; a non-matching user returns False).
- Lock names: `"intake"`, `"pending"`, `"drive_sync"`, `"sheet_push"`. `app.state.lock` stays only for the `running` set.

- [ ] **Step 1: Failing tests**

```python
def test_cannot_answer_another_accounts_approval():
    b = ApprovalBroker()
    aid = b.request("u_a")
    assert b.resolve(aid, True, user_id="u_b") is False
    assert b.resolve(aid, True, user_id="u_a") is True

def test_locks_are_per_account():
    assert user_lock("pending", "u_a") is user_lock("pending", "u_a")
    assert user_lock("pending", "u_a") is not user_lock("pending", "u_b")
```

Plus `test_two_accounts_commit_at_once` in `tests/integrations/test_writer.py`: two threads call `apply_change` on `users/u_a` and `users/u_b` plans of the same repo; both succeed and `git log` has two commits.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `/approvals/{id}` passes `request.state.user_id`.
- [ ] **Step 4: Run** `uv run pytest -q` → pass.
- [ ] **Step 5: Commit** `fix: per-account approvals and locks, one git lock`

### Task 5: Google per account, no shared Drive or Sheet

**Files:**
- Modify: `server/config.py` (`GoogleConfig` keeps `client_file` only)
- Modify: `server/users.py` (`user_config` reads `drive_folder_id`/`sheet_id` from `users/<id>/settings.yaml` only)
- Create: `server/google_settings.py` with `save_google_settings(cfg, drive_folder_id: str | None, sheet_id: str | None) -> None` (writes `settings.yaml`, commits `data: google settings` under `repo_lock`)
- Modify: `server/api/google.py` (per-user `GoogleAuth` cache `app.state.google_auth: dict[str, GoogleAuth]`; PKCE `_pending` map stays per object, so the callback must hit the same user's object — it does, the session cookie is sent on the redirect back); `_redirect` from origin; `PUT /api/google/settings`
- Modify: `server/api/settings.py` (GET returns `google: {drive_folder_id, sheet_id}` for the user)
- Modify: `server/finance/drive_inbox.py`, `server/finance/sheet_copy.py`, `server/loops/builtin.py:46`, `server/loops/service.py:35`, `server/cli.py:149,156` (missing id → `GoogleSetupMissing` with the exact Global Constraints message)
- Modify: `ui/src/features/settings/GoogleSection.tsx`, `ui/src/lib/api.ts`
- Test: `tests/api/test_google.py`, `tests/finance/test_drive_inbox.py`

**Interfaces:**
- Produces: `class GoogleSetupMissing(Exception)` in `server/integrations/google/oauth.py`; `require_drive(cfg) -> str`, `require_sheet(cfg) -> str` there.
- Produces: `_redirect(request) -> str` = `f"{proto}://{host}/api/google/callback"` with `proto`/`host` from `X-Forwarded-Proto`/`X-Forwarded-Host` when the client is a trusted proxy (Task 2's `client_ip` trust set), else the request URL.
- Agent path: the finance toolkit tools that touch Drive or Sheet catch `GoogleSetupMissing` and return its message as the tool result. API sync/push return 409 with it. Jobs skip the account and log one line.

- [ ] **Step 1: Failing tests**

```python
def test_google_tokens_are_per_account(make_client, tmp_path):
    a, b = make_client(user="u_a"), make_client(user="u_b")   # same app, two sessions
    a.app.state.google_auth_for("u_a").save(FakeCreds("a"))
    b.post("/api/google/disconnect")
    assert a.get("/api/google/status").json()["connected"] is True

def test_no_drive_folder_says_so(ctx_without_google_ids):
    with pytest.raises(GoogleSetupMissing, match="Drive folder is not set up yet"):
        require_drive(ctx_without_google_ids.config)
```

(If `make_client` cannot give two sessions on one app, extend it with a `user=` argument that calls `add_account(cfg, user)` and returns a client with that cookie; `app.state.google_auth_for(user_id) -> GoogleAuth` is the accessor the route uses.)

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** GoogleSection gets two text fields (Drive folder id, Sheet id) with Save, using `.field` and `button.secondary`.
- [ ] **Step 4: Run** `uv run pytest -q && cd ui && npx vitest run` → pass.
- [ ] **Step 5: Commit** `fix: Google connection, Drive folder and Sheet per account`

### Task 6: Background jobs per account, time zones, CLI

**Files:**
- Modify: `server/api/app.py` (`_as_owner` → `for_each_account`; nightly becomes one hourly job; drive_sync per account)
- Modify: `server/scheduler.py` (`nightly_job` lock per account via `user_lock("nightly", user)`; `today` = `local_today(cfg)`)
- Modify: `server/users.py` (add `local_today`, `user_tz`)
- Modify: `server/agent/tools/registry.py` (`ToolContext.today` defaults to `local_today(self.config)` via `__post_init__` when not given)
- Modify: `server/loops/triggers.py` (`_add` passes `timezone=user_tz(user_config(cfg, user_id))` for cron)
- Modify: `server/cli.py` (`--user USERNAME`; `ka users list`, `ka users reset-password USERNAME`; `ka check` without accounts prints `ok: config valid; no accounts yet`)
- Test: `tests/test_jobs.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `for_each_account(cfg: Config, job: Callable[[Config], None], name: str) -> Callable[[], None]` — returns a scheduler callable that, per account in `users` order, runs `job(user_config(cfg, user))` under `user_lock(name, user)` (non-blocking acquire; skip if busy), catches and logs every exception per account.
- Produces: `user_tz(cfg: Config) -> ZoneInfo` (profile `timezone`, else server local); `local_today(cfg: Config) -> date`.
- Ruling: nightly extraction runs hourly for every account and extracts up to that account's local yesterday (catch-up is idempotent via `last_extraction_day`), replacing the fixed 03:00 server-time run.
- Produces: CLI `resolve_user(db, username: str | None) -> str` — None with exactly one account → it; None with zero → `UserError("no accounts yet: sign up in the app")`; None with several → `UserError("several accounts: pass --user USERNAME")`; unknown → `UserError("no account named <username>")`.

- [ ] **Step 1: Failing tests**

```python
def test_job_runs_for_every_account_even_if_one_fails(two_account_cfg):
    seen = []
    def job(ucfg):
        seen.append(ucfg.user_id)
        if ucfg.user_id == "u_a":
            raise RuntimeError("boom")
    for_each_account(two_account_cfg, job, "test")()
    assert seen == ["u_a", "u_b"]

def test_today_uses_the_accounts_time_zone(cfg_with_tz):  # profile timezone Pacific/Kiritimati
    assert local_today(cfg_with_tz) == datetime.now(ZoneInfo("Pacific/Kiritimati")).date()

def test_cli_needs_user_when_several(two_account_cfg, capsys):
    assert main(["pending"]) == 1
    assert "pass --user USERNAME" in capsys.readouterr().err
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `reset-password` prompts twice with `getpass`, enforces `MIN_PASSWORD`, revokes that account's sessions.
- [ ] **Step 4: Run** `uv run pytest -q` → pass.
- [ ] **Step 5: Commit** `fix: background jobs, time zone and CLI per account`

### Task 7: Home, sign-up and sign-in screens

**Files:**
- Create: `ui/src/features/auth/WelcomePage.tsx`, `ui/src/features/auth/SignedOut.tsx` (redirect guard)
- Modify: `ui/src/app/routes.tsx` (`/welcome`, `/signup`, `/login` under `SignedOut`)
- Modify: `ui/src/app/Shell.tsx` (signed out → `<Navigate to="/welcome" replace />`; no `SetupStep` here)
- Modify: `ui/src/features/auth/SetupStep.tsx` → rename `SignupPage.tsx` (rules from `useQuery(keys.auth)`; link "Already have an account? Sign in")
- Modify: `ui/src/features/auth/LoginPage.tsx` (drop `setup_needed` branch; link "New here? Create an account"; `qc.clear()` before navigating)
- Modify: `ui/src/features/auth/session.ts` (return path and draft stored with `username`; `takeReturn(username)` / `takeDraft(username)` drop entries for another username)
- Modify: `ui/src/features/chat/Entity.tsx` (optional `lights?: number`; when set, the pending query is disabled)
- Modify: `ui/src/features/settings/SettingsPage.tsx` (username above Sign out; sign out → `/welcome`)
- Modify: `ui/src/lib/api.ts` (`signup`, `AuthStatus` without `setup_needed`, with `username`)
- Modify: `ui/src/styles.css` (welcome layout; keyboard-safe scrolling)
- Test: `ui/src/features/auth/session.test.ts`, `ui/src/features/auth/routes.test.tsx`

**Interfaces:**
- Consumes: Task 1 `/api/auth/status` and `/api/auth/signup`.
- Produces: `SignedOut` renders its child only when `auth.user` is null, else `<Navigate to="/chat" replace />`.
- `onUnauthorized` stores `{path, draft, username}` using the last known username from the auth query cache; `LoginPage` passes the signed-in username to `takeReturn`.

Design (reuse, do not invent): app frame (`.app`, `header.bar`, `.textbtn.wordmark`, `main.screen`), `.col.page.onboarding`, `.lead`, `button.primary`/`button.secondary`, colour tokens, `ka-fade`/screen entry animation. Welcome: `Entity mode="empty" lights={0}` centred in the upper half; title "Ka" (28px, as onboarding h1); lead "Your data and one agent that knows you."; on phones Create account (primary) and Sign in (secondary) stacked full width at the bottom above `env(safe-area-inset-bottom)`, on desktop side by side under the lead. Inputs 16px; `scroll-padding-bottom` on `main.screen` so the focused field and the bottom button stay visible above the iOS keyboard; `autocomplete="username"` / `new-password` / `current-password` for Keychain.

- [ ] **Step 1: Failing tests**

```ts
test('a draft saved by one account is not restored for another', () => {
  saveReturn('/chat/C-1', 'half a message', 'avery')
  expect(takeReturn('blake')).toBeNull()
  expect(takeDraft('blake')).toBe('')
})

test('signed-out visitors land on the home screen', async () => {
  mockAuth({ user: null })
  renderAt('/chat')
  expect(await screen.findByRole('button', { name: 'Create account' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
})
```

- [ ] **Step 2: Run** `cd ui && npx vitest run` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx tsc -b && npm run lint && npx vitest run && npm run build` → pass; then check `/welcome`, `/signup`, `/login` in the browser pane at 375×812 and desktop, light and dark, keyboard open on a field.
- [ ] **Step 5: Commit** `feat: home, sign-up and sign-in screens`

### Task 8: Docs say many accounts

**Files:**
- Modify: `context/flows/login.md`, `google.md`, `nightly-extraction.md`, `data-repo.md`, `config.md`, `flags.md`, `loops.md`, `context/decisions.md` (withdraw line 370's one-account decision, add the multi-account decision), `context/index.md` (new files), `Docs/next-phase-plan.md` (note at the top that accounts are now open), `Docs/post-build-setup.md` (Google test users, redirect URI, no data claim, delete old `ka.db`), `AGENTS.md` (`ka users`, `--user USERNAME`).
- Modify docstrings: `server/auth/ratelimit.py`, `server/auth/users.py:1`, `server/users.py:1-5`.

- [ ] **Step 1:** Use the `flow-docs` skill for each flow doc; every mention of "one account", "the owner" as the only user, `setup`, `claim_legacy_data`, `backfill_user`, `only_user` is gone (`grep -rnE "one account|claim_legacy|backfill_user|only_user|auth/setup|setup_needed" context Docs AGENTS.md server ui/src` → only historical plan files).
- [ ] **Step 2: Run** `uv run pytest -q && uv run ruff check . && cd ui && npx vitest run` → pass.
- [ ] **Step 3: Commit** `docs: Ka is multi-account`
