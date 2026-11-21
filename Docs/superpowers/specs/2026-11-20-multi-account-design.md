# Ka multi-account platform: design

Date: 2026-11-20. Status: draft for the owner's approval.

## Intent

Ka becomes a normal platform: anyone who can reach it signs up, gets their own Ka, and goes
through onboarding. Returning people sign in. Every capability works for every account, and no
account can see, change or block another account's data or work. The owner was never
asked to keep Ka single-account; the earlier "one account" rule is withdrawn.

## Goals

- A home screen with two ways in: **Create account** (then onboarding) and **Sign in**.
- Open sign-up, many accounts, full isolation: data files, database rows, search, approvals,
  Google connection, background jobs, locks, UI caches.
- Every background job runs once per account.
- When an account has no Drive folder or Sheet, the agent says so plainly instead of using
  anyone else's.
- A professional, modern UI for the new screens that reuses the existing design (tokens,
  onboarding layout, the Ka ring) and works as an installed PWA on iOS and Android.
- Docs and tests say "many accounts" everywhere.

## Non-goals

- Moving existing data: there is no real data yet. `claim_legacy_data` and `backfill_user`
  are deleted; every account starts empty.
- Email, password reset by email, social login, account deletion from the UI, admin UI,
  per-account models or flags (models and flags stay platform settings in `config.yaml`).
- Invite codes. They can be added later behind the same sign-up screen.
- A per-account spending cap (owner's call: not needed). Loop runs keep their existing
  per-run limits.
- Hiding one account's data from the server operator: all accounts share one data repo and
  one SQLite file on the host.

## Anti-goals (a failure even if it works)

- Any path where account B reads, writes, resolves, deletes or blocks account A's things.
- An account using another account's Google token, Drive folder, Sheet or unsent draft.
- A background job that silently skips accounts.
- New screens that look like a different app from chat and onboarding.

## Constraints

- Stack stays: FastAPI, SQLite, git data repo, React PWA. No new services.
- Login stays always on, no flag (owner's rule).
- Money is `Decimal`; no personal data in the code repo; flow docs change with the code.
- Ka is reachable over the tailnet today (`tailscale serve` HTTPS proxy to 127.0.0.1:8000).

## Approaches considered

- **A. Open sign-up with limits (chosen).** Anyone who reaches Ka can create an account.
  Sign-up is rate limited per client address.
- **B. Invite codes.** Safer on the open internet, one more step per person. Deferred.
- **C. Separate data repo and database per account.** Strongest isolation, much more code and
  ops. Rejected: the shared repo with `users/<id>/` plus scoped rows already gives isolation.

## Design

### 1. Accounts and sign-up

- `POST /api/auth/signup` replaces `/auth/setup`. Open always; no "first account" rule.
- The user id is an opaque random id (`u_` + 12 hex), not the username. The folder is
  `users/<user_id>/`. A recycled username never inherits an old folder, and usernames cannot
  be guessed from paths. Usernames stay unique, lower case, `^[a-z][a-z0-9_-]{2,31}$`.
- Sign-up creates the user, copies `server/users_starter/` into the new folder, commits it
  (`data: start users/<id>`), adds built-in loop tasks (`on_user_created`), and signs in.
- Sign-up is limited per client address (5 per hour) on the same limiter type as login.
- `/api/auth/status` returns `{user, username, min_password, username_rule}`;
  `setup_needed` goes away.
- Deleted: `claim_legacy_data`, `backfill_user`, `only_user`, the `Config.user_id` field in
  `config.yaml` (still set in memory by `user_config`).
- `Db(path, user_id)` makes `user_id` required; `LOCAL_USER` goes away except in tests.

### 2. Login protection

- Login limit keyed on client address plus username. Client address comes from
  `X-Forwarded-For` only when the request comes from 127.0.0.1 (the tailnet proxy).
- Lockout becomes backoff per username-and-address: after 5 failures from one address that
  address waits 15 minutes for that username; other addresses are not locked. One person
  can no longer lock another out.
- Login and sign-up answer the same way for "no such user" and "wrong password".

### 3. Data isolation in SQLite

- Ids: conversation, intake job and task ids use `token_hex(8)` (no cross-account collision
  on the shared primary key).
- `message_fts` gains `user_id`; search filters on it. Migration step 3 rebuilds the FTS table.
- `add_message` and every by-id read or write check the row belongs to `db.user_id`
  (`list_conversations` subqueries too).

### 4. Shared server state

- Approvals: the broker stores the owning `user_id`; `/approvals/{id}` resolves only the
  caller's own.
- Google auth: one `GoogleAuth` per account (keyed by `user_id`), so tokens, status and
  disconnect are per account. The OAuth redirect URL is built from the request's own origin
  (works behind the tailnet HTTPS proxy), not hard-coded `127.0.0.1`.
- Locks: `app.state.lock`, `pending_lock`, the Drive sync and Sheet push locks become per
  account (a dict of locks keyed by `user_id`).
- Git: one commit lock at the data repo root for all accounts, and the commit hash comes
  from the commit itself, not a later `rev-parse HEAD`.

### 5. Google Drive and Sheet per account

- `user_config` no longer falls back to `config.yaml`'s `drive_folder_id` and `sheet_id`;
  those fields are removed from `config.yaml`. Each account sets its own in Settings
  (stored in `users/<id>/settings.yaml`, as today).
- When a tool or job needs one that is missing, it returns a clear message, for example
  "Your Google Drive folder is not set up yet. Add it in Settings to import statements."
  The agent relays it; jobs skip that account and log one line.

### 6. Background jobs

- One helper, `for_each_account(cfg, fn)`, runs a job once per account, each with its own
  `user_config`, its own lock, and errors caught per account (one account's failure never
  stops the others).
- Nightly extraction and Drive sync use it (replacing `_as_owner`). Loops already run per
  account.
- Time zone: each account's `profile.timezone` (default: the server's) is used for the
  agent's "today", the hourly nightly-extraction run (each account up to its local yesterday) and loop cron triggers.

### 7. CLI

- `--user USERNAME` is required whenever there is more than one account, and it must exist.
- New `ka users list` and `ka users reset-password USERNAME` (prompts for the new password)
  for the operator.

### 8. UI

Routes:

| Path | Signed out | Signed in |
|---|---|---|
| `/welcome` | Home | redirect to `/chat` |
| `/signup` | Account step (1 of 6), then `/onboarding` | redirect to `/chat` |
| `/login` | Sign in, then the saved return path or `/chat` | redirect to `/chat` |
| everything else | redirect to `/welcome` | app |

Home screen (`WelcomePage`):

```
[status bar, safe area]
 Ka                                   (same header as the app)

            ( Ka ring, idle motion )

         Ka
         Your data and one agent
         that knows you.

 [ Create account ]   primary, full width on phones
 [ Sign in ]          secondary
```

- Reuses the app frame (`header.bar`, `main.screen`), colour tokens, type scale, the
  onboarding page layout, `button.primary` and `button.secondary`, and the empty-chat Ka
  entity (`Entity mode="empty" lights={0}`).
- Sign-up and sign-in keep `AuthFrame`; each links to the other ("Already have an account?
  Sign in", "New here? Create an account").
- Phones and installed PWA: buttons sit at the bottom inside the safe area; the layout uses
  `100dvh` and `env(safe-area-inset-*)`; inputs are 16px (no iOS zoom); the page scrolls
  when the keyboard opens so the focused field and button stay visible; correct
  `autocomplete` so iOS Keychain offers to save and fill the password; the PWA start URL
  `/chat` redirects to `/welcome` when signed out.
- Account safety in the browser: on sign-in or sign-up the query cache is cleared
  (`qc.clear()`), and the saved return path and unsent draft carry the username and are
  dropped when a different account signs in.
- Settings shows the signed-in username next to Sign out.

### 9. Docs

Update in the same change: `context/flows/login.md`, `google.md`, `nightly-extraction.md`,
`data-repo.md`, `config.md`, `flags.md`, `loops.md`, `context/decisions.md` (withdraw the
one-account decision, add this one), `Docs/next-phase-plan.md` notes, `AGENTS.md` (serve
address), `Docs/post-build-setup.md` (Google test users and redirect URI, no account claim).

### 10. Tests (one per risky behaviour)

- Two accounts: neither sees the other's conversations, search hits, pending cards, loop tasks
  or files.
- Approval of another account's tool call is refused.
- Google: account B's connect does not touch account A's token.
- Background job runs for both accounts and one failing does not stop the other.
- Missing Drive folder gives the plain message and no access to another account's folder.
- Login lockout from one address does not block the same username from another.
- UI: a draft saved by account A is not restored for account B.

## Left to the builder

Exact copy on the home screen, the idle ring's motion values, the migration code for the
FTS rebuild, the per-account lock helper's shape, and how the backoff is stored.

## Owner steps after the build

- In Google Cloud, add each person as a test user (or publish the app) and add the tailnet
  HTTPS callback URL as an authorised redirect URI.
- Delete the old `ka.db` and root-level personal files, since nothing moves across.
