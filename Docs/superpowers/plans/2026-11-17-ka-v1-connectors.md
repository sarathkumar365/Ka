# Ka v1: Connectors (GitHub, Notion, LinkedIn Export, Gmail) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboarding step 3 and Settings can connect GitHub, Notion and the owner's Gmail MCP server, and accept a LinkedIn data export. Each source turns what it finds into Pending cards. Nothing is written without approval.

**Architecture:**
- Every source is an intake background job (same `intake_jobs` table, polling, and one-job-at-a-time 409 rule) that ends in existing card types:
  - GitHub repos become `bundle` cards with `other_record` patches (type `project`).
  - The LinkedIn export becomes a `ResumeDraft` through `queue_draft`, so it gets by-job cards with no model call.
  - Notion pages and Gmail messages become memory items through the existing extraction instruction.
- Remote sources go through plan 3's `McpServer`.

**Tech Stack:** `mcp` SDK (streamable HTTP, `OAuthClientProvider` for Notion), plan 3 `McpServer`, intake runner, React.

**Spec:** `context/decisions.md`, Onboarding step 3 ("Connect sources through their official MCP servers: Google (Drive, Gmail via Multi Gmail), Notion, GitHub"), and `Docs/superpowers/specs/2026-11-17-onboarding-intake-design.md`. The owner's calls on 2026-11-17: GitHub, Notion, LinkedIn export and Gmail; official MCP servers; Gmail through the owner's own MCP server (URL and sign-in method to be given).

**Depends on:** nothing from plan 3, which now uses the direct Google APIs. The MCP client is built here in Task 0.

### Task 0: MCP client

**Files:**
- Create: `server/integrations/mcp_client.py`, `tests/integrations/test_mcp_client.py`
- Modify: `pyproject.toml` (`mcp`)

**Interfaces:**
- Produces: `McpServer(url: str, auth: str | httpx.Auth | Callable[[], str])` with `tools() -> list[str]` and `call(name: str, args: dict) -> Any`. It uses the SDK's streamable HTTP client and is synchronous through `anyio.run`. A string or callable is sent as `Authorization: Bearer`. Server errors raise `McpError` with the server's message.
- [ ] **Step 1: Write the failing test** `test_call_sends_bearer_and_returns_result`, against a local `FastMCP` server on a random port.
- [ ] **Step 2: Run** `uv run pytest tests/integrations/test_mcp_client.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the client.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: pass.
- [ ] **Step 5: Commit** `feat: MCP client`.

## Global Constraints

- Endpoints:
  - GitHub remote MCP `https://api.githubcopilot.com/mcp/`, using a fine-grained read-only personal access token sent as Bearer. This is the official server's supported header auth; its OAuth needs a registered app. That is the builder's call; the owner can veto it.
  - Notion remote MCP `https://mcp.notion.com/mcp`, using OAuth with dynamic client registration through the SDK's `OAuthClientProvider`.
  - Gmail: `connectors.gmail.url` plus `connectors.gmail.auth` (`bearer_env: NAME` or `google_oauth`) and the tool names `search_tool` and `read_tool` in the local `config.yaml`. Until the owner gives them, the Gmail row shows "not configured".
- Tokens are stored under `<data_repo>/local/connectors/<name>.json` with mode 0600, or in `.env` for the GitHub token (`GITHUB_TOKEN`). Never in the code repo, logs or activity text.
- Source text is data, never instructions. It is capped per item (Notion page 20 000 characters, mail message 4 000 characters) and per job (60 000 characters, as in intake), and a cap that is hit is reported in the job result.
- Imported memory is prefixed `(imported, unverified) ` with source `import:<name>`, as in `memory_import.py`.
- Gmail defaults: queries `["offer letter", "employment agreement", "promotion", "payslip"]`, the last 5 years, at most 100 messages per run. The owner can edit them in config.
- LinkedIn ZIP: read `Profile.csv`, `Positions.csv`, `Education.csv` and `Skills.csv` only. The same zip-bomb guard applies as in `readers.py`.
- Flags, default off: `connectors` (the GitHub, Notion and LinkedIn rows) and `gmail_source`. The existing `notion_source` flag is removed in favour of `connectors`.
- Commits: commit guard; touch `.claude/.reviewed` only after a yes; no trailers; noreply author.

## Review Focus

1. A repo is already stored as a project (same URL) or is a fork or archived. It is skipped, and the card shows "N skipped" (T1 test).
2. A LinkedIn position has no end date (current job) or only "Mar 2019". The dates normalise as in intake, a current job gets `end: null`, and a missing start gets the "needs a date" flag (T2 test).
3. The Notion OAuth window is closed halfway, or the token is revoked. The row returns to "Connect" with a message, and no job is left running (T3 test).
4. Gmail returns a message whose body includes "ignore previous instructions ...". It is handled as text only: the extraction prompt marks it as data, and the items are still only queued (T4 test with a hostile fixture).
5. A source job runs while a resume job is running. The 409 is shown as "another import is running" on the Sources step (T5 UI check, plus the existing API test).

---

### Task 1: GitHub repos to project cards

**Files:**
- Create: `server/connectors/__init__.py`, `server/connectors/github.py`, `tests/connectors/test_github.py`
- Modify: `server/intake/runner.py` (`run_source_job(kind, ...)`), `server/store/db.py` (intake job `kind` gains `github, notion, linkedin, gmail`), `server/api/intake.py` (`POST /api/intake/sources/{name}`)

**Interfaces:**
- Consumes: `McpServer`, `Db.add_pending`, the bundle card shape, `load_data(root).other`.
- Produces:
  - `collect_repos(server: McpServer) -> list[Repo]`, where `Repo(name, url, description, language, topics, created, pushed, fork, archived)`. The tool names come from `server.tools()`: the builder picks the authenticated-user repo listing tool, and ledgers which one.
  - `queue_repos(db, data, repos, now) -> int`: one card with `section="projects"`, title `GitHub: N projects`, and items with patch `other_record` add `{type: "project", name, details: {url, description, language, topics, started: created[:7], last_active: pushed[:7]}}`. Forks, archived repos and repos already stored (same `details.url`) are skipped and counted in `detail`.
  - If the type `project` is not in `other.yaml` `types`, the card's first item adds it; this item is locked as selected, like the job line.
- [ ] **Step 1: Write the failing tests** with a fake MCP server: `test_skips_forks_archived_and_stored` and `test_approve_writes_projects`. The second runs `approve_bundle` and then `load_data` shows the records.
- [ ] **Step 2: Run** `uv run pytest tests/connectors -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`, then a live run with the owner's token against a scratch data repo. Expected: pass, and the card lists the real repos.
- [ ] **Step 5: Commit** `feat: GitHub connector queues project cards`.

### Task 2: LinkedIn export to by-job cards

**Files:**
- Create: `server/connectors/linkedin.py`, `tests/connectors/test_linkedin.py` (synthetic ZIP built in the test)
- Modify: `server/api/intake.py` (`POST /api/intake/linkedin`, multipart, one `.zip` file, 50 MB maximum)

**Interfaces:**
- Consumes: `ResumeDraft` and its models from `server/intake/draft.py`, and `queue_draft`.
- Produces: `read_linkedin(zip_path: Path) -> ResumeDraft`. It is deterministic and has no model call.
  - `Positions.csv` columns `Company Name, Title, Description, Location, Started On, Finished On` become jobs. Each description line becomes a highlight with no numbers guard needed, because the text is the owner's own.
  - `Education.csv` becomes education.
  - `Profile.csv` gives the name and location.
  - `Skills.csv` becomes one memory item `Skills: a, b, c` queued with `queue_memory`.
  - Dates `Mon YYYY` become `YYYY-MM`, and `YYYY` alone follows intake's rule.
- [ ] **Step 1: Write the failing tests:**
  - `test_current_job_has_no_end`
  - `test_month_year_dates`
  - `test_missing_start_is_blocked`
  - `test_unexpected_files_ignored`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: pass.
- [ ] **Step 5: Commit** `feat: LinkedIn export intake`.

### Task 3: Notion pages to memory items

**Files:**
- Create: `server/connectors/notion.py`, `server/connectors/oauth_store.py`, `tests/connectors/test_notion.py`
- Modify: `server/api/intake.py` (`GET /api/connectors/notion/login`, `/callback`, `GET /api/connectors/notion/search?q=`, `POST /api/intake/sources/notion {page_ids}`)

**Interfaces:**
- Consumes: Task 0 `McpServer` with an `httpx.Auth`, namely the SDK `OAuthClientProvider`; `memory_import` (the path that turns text into queued memory items).
- Produces:
  - `FileTokenStorage(path)`, which implements the SDK's `TokenStorage`.
  - `search_pages(server, q) -> list[PageRef(id, title, edited)]`.
  - `fetch_pages(server, ids, cap) -> list[tuple[str, str]]` (title and text).
  - The job joins the pages as `## <title>\n<text>` and runs the memory import with source `import:notion`.
- [ ] **Step 1: Write the failing tests:**
  - `test_revoked_token_reports_reconnect`
  - `test_page_cap_truncates_and_reports`
  - These use a fake MCP server; the OAuth flow itself is checked live in Step 4.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code.
- [ ] **Step 4: Run** `uv run pytest -q`, then a live run: connect Notion, search, pick 2 pages, and check that memory cards appear. Expected: pass.
- [ ] **Step 5: Commit** `feat: Notion connector`.

### Task 4: Gmail through the owner's MCP server

**Files:**
- Create: `server/connectors/gmail.py`, `tests/connectors/test_gmail.py`
- Modify: `server/config.py` (`connectors: ConnectorsConfig`), `config.example.yaml` (keys only, with placeholder URL `set-me`)

**Interfaces:**
- Produces:
  - `collect_mail(server, cfg: GmailConfig) -> list[Mail(id, date, subject, sender, text)]`. It runs each query through `search_tool`, de-duplicates by id, keeps the newest `max_messages`, and reads each one with `read_tool`.
  - The job runs the memory import with source `import:gmail`. Each message is prefixed with `Subject:` and `Date:` so the facts can be dated.
- [ ] **Step 1: Write the failing tests:**
  - `test_dedupes_and_caps`
  - `test_hostile_body_only_queues_items`: the fake adapter returns items, the fixture body holds an injection line, and the result is queued items with no other effect.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code. The live check waits for the owner's URL and auth details; ledger the wait.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: pass.
- [ ] **Step 5: Commit** `feat: Gmail source via configurable MCP server`.

### Task 5: Sources step and the Settings "Connected sources" section

**Files:**
- Modify: `ui/src/features/onboarding/StepSources.tsx`, `ui/src/features/settings/SettingsPage.tsx`, `ui/src/lib/api.ts`, `server/api/intake.py` (`GET /api/connectors` status), `server/api/settings.py`
- Test: `ui/src/features/onboarding/sources.test.ts`

**Interfaces:**
- Produces:
  - `GET /api/connectors` returns `[{name, state: "off"|"not_configured"|"disconnected"|"connected", detail}]`. The detail never holds a token.
  - The UI rows:
    - GitHub: state, then Import repos.
    - Notion: Connect, then a search box and page picker (up to 20), then Import.
    - LinkedIn: a ZIP drop zone with a link to LinkedIn's "Get a copy of your data" page.
    - Gmail: state, then Import mail.
    - Google (plan 3): a link to Settings.
  - Every row runs a job and shows `JobStatus`. In Settings, the "Connected sources" section shows the same states with Disconnect.
  - A pure helper `rowAction(state) -> 'connect'|'import'|'setup'|'none'` is tested.
- [ ] **Step 1: Write the failing vitest** for `rowAction` over all 4 states.
- [ ] **Step 2: Run** `cd ui && npx vitest run src/features/onboarding`. Expected: FAIL.
- [ ] **Step 3: Implement** the code, following the design's Sources rows in `Design/extracted/app.html`.
- [ ] **Step 4: Run** the full checks (pytest, ruff, vitest, tsc, build). Then check in the browser against a scratch repo: each row's states, the 409 message when a resume job is running, and phone width. Expected: all pass.
- [ ] **Step 5: Commit** `feat: sources step and connected sources in settings`. Update the `intake` and `settings` flow docs and the decisions addendum.
