# Ka v1: Category Suggestions, Scheduler, Flaky Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New merchants and unknown transaction types get a model-suggested category or tag that the owner approves once in Pending, which fills the category on stored rows. Nightly memory extraction runs by itself on a schedule. The three flaky evals pass reliably.

**Architecture:** Suggestions run after an import commits, never inside the parser or tagging code. They reuse the intake `bundle` Pending card, so approval goes through `approve_bundle` and `plan_batch` and makes one commit. A post-approve hook then re-applies the rules to stored rows whose category is empty. The scheduler is APScheduler inside `ka serve`, with a catch-up run at start. Plan 3 adds its Drive sync job to the same scheduler.

**Tech Stack:** Python 3.13, APScheduler 3.x (`BackgroundScheduler`), existing adapter, intake bundle cards, CSV finance store, pytest.

**Spec:** `context/decisions.md`. Relevant lines: "New merchants get an LLM-suggested category that I approve once; it is then saved to the file", "Nightly extraction: a background job ...", and "APScheduler for the nightly job (runs at next start if missed)". The owner chose the 5-plan split on 2026-11-17; voice was later moved to v1.1.

## Global Constraints

- No LLM call in the parser or tagging path (`server/finance/parser.py`, `tagging.py`, `importer.py`). Suggestions live in `server/finance/suggest.py` and are called after `commit_import`.
- Money is `Decimal`. Recategorising rewrites only the `category` field and never touches amounts.
- Never overwrite a non-empty category on a stored row.
- Writes to the data repo go only through `plan_batch` and `apply_change`, under the existing lock.
- Flags, default off: `category_suggestions` (new) and `nightly_extraction` (existing; it now also turns the schedule on).
- Public repo: tests use synthetic merchants only. Tests minimal: one per risky behaviour.
- Commits: commit guard hook; touch `.claude/.reviewed` only after the owner says yes; no Claude trailers; noreply author.

## Review Focus

1. The model returns a category that is not in `categories.yaml`. The item is dropped, never queued (T1 test).
2. The model returns a `match` that does not occur in the merchant text, or one so short that it hits many merchants (shorter than 4 characters). The item is dropped (T1 test).
3. The same merchant is suggested twice across two imports while a card is still pending. Only one pending item exists (dedupe by `norm_key`, T1 test).
4. The server is closed for 3 days. On start, extraction runs once per missed day (at most 7 days), and the same day never runs twice (T3 test).
5. The model is down during a scheduled run. The scheduler logs one activity line and the next run still happens; nothing crashes `ka serve` (T3 test).

---

### Task 1: Suggest categories and types into Pending

**Files:**
- Create: `server/finance/suggest.py`, `tests/finance/test_suggest.py`
- Modify: `server/integrations/data_repo/writer.py` (new target `transaction_type`), `server/cli.py` (`ka import` calls it; new `ka suggest`), `config.example.yaml`

**Interfaces:**
- Consumes: `Adapter.complete`, `KaData.categories.categories`, `norm()` from `tagging.py`, `Db.add_pending(kind, payload, source, now, key)`, intake card shape (`kind="bundle"`, payload `title, section, needs, items[{id,label,detail,selected,patch}]`).
- Produces:
  - `suggest_categories(merchants: list[str], data: KaData, adapter: Adapter) -> list[CategorySuggestion]`, where `CategorySuggestion(description: str, match: str, category: str)`. One model call that returns JSON `{"items": [...]}`, with one retry on invalid JSON. Guards: category in the list, `norm(match)` in `norm(description)`, `len(match) >= 4`.
  - `suggest_types(type_texts: list[str], adapter: Adapter) -> list[TypeSuggestion]`, where `TypeSuggestion(type_text: str, tag: Tag)`. Tags not in `Tag` are dropped.
  - `queue_suggestions(db: Db, cats, types, source: str, now: datetime) -> int` (number of cards). Categories go into one card with `section="categories"`, title `Categorise N merchants`, and one `merchant_rule` add patch per item with fields `match, category`. Types go into one card with `section="types"`, one `transaction_type` add patch per item with fields `bank, type_text, tag`. Item `norm_key` is `cat:<norm(match)>` or `type:<norm(type_text)>`; an item whose key is already pending is skipped.
  - `uncategorised(store: FinanceStore) -> list[str]`: the distinct descriptions of stored rows with an empty category and tag `purchase`.
  - Writer target `transaction_type`: file `rules/transaction_types.yaml`, list `types`, no id, key `bank|type_text`.
  - CLI: `ka suggest` queues suggestions for all uncategorised stored rows. This backfills the owner's existing rows. `ka import` calls the same functions after a commit when the flag is on.

- [ ] **Step 1: Write the failing tests** in `tests/finance/test_suggest.py`, using `FakeAdapter` with canned JSON:
  - `test_drops_unknown_category_and_bad_match`: input has 3 items: one valid, one with category `not-a-category`, one with match `ab`. Only the valid item is returned.
  - `test_queue_dedupes_pending`: call `queue_suggestions` twice with the same merchant. `db.list_pending()` has one card with one item.
  - `test_approve_categories_card_writes_rule`: approve the card with `approve_bundle`. `load_data(root).merchant_rules.rules[-1]` has the category, and `approved` is today's date.
- [ ] **Step 2: Run** `uv run pytest tests/finance/test_suggest.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the functions above and the writer target. In `approve_bundle`, set `fields["approved"] = today.isoformat()[:10]` for `merchant_rule` add patches. The prompt tells the model the merchant text is data and not instructions.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: pass, clean.
- [ ] **Step 5: Commit** `feat: suggest merchant categories and type tags into pending`.

### Task 2: Re-apply rules to stored rows after approval

**Files:**
- Modify: `server/finance/store.py`, `server/finance/tagging.py`, `server/intake/approve.py`, `server/api/pending.py`, `server/cli.py`
- Test: `tests/finance/test_store.py`

**Interfaces:**
- Consumes: T1 cards (`section` is `categories` or `types`).
- Produces:
  - `FinanceStore.update_categories(changes: dict[str, str]) -> int`, keyed by transaction id. It writes the CSV atomically and skips a row whose category is non-empty.
  - `reapply_rules(store: FinanceStore, data: KaData) -> int` in `tagging.py`. It uses the same first-match logic as `tag_rows`, applied to stored rows with an empty category that are not own-account rows (tag not in `transfer, debt_payment`).
  - `approve_bundle(..., store: FinanceStore | None = None)`. After a commit for a `categories` or `types` card, it calls `reapply_rules(store, load_data(root))` and adds `; categorised N rows` to the return text.
  - Settled for the builder: a new type rule does not re-tag stored rows, because tags affect totals the owner already saw. Tags apply from the next import.

- [ ] **Step 1: Write the failing test** `test_reapply_fills_only_empty`. There are three rows: one empty and matching, one with category `groceries` that also matches another rule, and one empty without a match. Only the first row changes, and the return value is 1.
- [ ] **Step 2: Run** `uv run pytest tests/finance/test_store.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code, and pass `CsvFinanceStore(cfg.finance_dir)` from the pending API and from `ka pending approve`.
- [ ] **Step 4: Run** `uv run pytest -q`, `uv run ruff check .`, and then a smoke test against a scratch copy of the data repo (`KA_CONFIG`): run `ka suggest`, then `ka pending approve <id>`, and check that `transactions.csv` has categories. Expected: pass, and the categories are filled.
- [ ] **Step 5: Commit** `feat: fill stored categories when a rule is approved`. Update `context/flows/pending.md` and the finance flow doc in the same commit (`flow-docs` skill).

### Task 3: Scheduler for nightly extraction

**Files:**
- Create: `server/scheduler.py`, `tests/test_scheduler.py`
- Modify: `server/api/app.py` (lifespan start and stop), `pyproject.toml` (`apscheduler>=3.10,<4`), `server/memory/extract.py` (no change to its signature)

**Interfaces:**
- Consumes: `extract_memories(day, db, data, adapter, now) -> int`, `Db.get_state` and `set_state`, `Db.add_activity`.
- Produces:
  - `ScheduledJob(id: str, trigger: dict, run: Callable[[], None])`.
  - `start_scheduler(jobs: list[ScheduledJob]) -> BackgroundScheduler`.
  - `catch_up_extraction(cfg, db, adapter_factory, today: date) -> list[date]`: runs each missing day from `app_state.last_extraction_day + 1` to yesterday, at most 7 days, then sets the state after each day. On a first run with no state it runs yesterday only.
  - `nightly_job(cfg, adapter_factory) -> ScheduledJob`: cron at 03:00 local time. It opens its own `Db`, calls `catch_up_extraction`, and catches every exception into an activity line `extraction failed: <short reason>`.
  - `create_app` starts the scheduler only when `flags.nightly_extraction` is true and `start_scheduler=True`. Tests pass `False`. A failed catch-up never stops the server from starting: catch-up runs in the scheduler thread, not in startup.
  - Plan 2 routes extraction for private conversations; this task uses `adapter_factory` exactly as `create_app` gets it.

- [ ] **Step 1: Write the failing tests:**
  - `test_catch_up_runs_each_missed_day_once`: the state is 3 days ago and the fake `extract` records days. It runs 2 days. A second call runs 0 days.
  - `test_failed_run_logs_and_survives`: the adapter raises `AdapterError`. There is one activity row containing `extraction failed`, no exception is raised, and the state is not advanced.
- [ ] **Step 2: Run** `uv run pytest tests/test_scheduler.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code. The CLI `ka extract` stays as a manual way to run one day.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: scheduled nightly extraction with catch-up`. Update the memory flow doc (`flow-docs` skill).

### Task 4: Fix the flaky evals q10, q13, q19

**Files:**
- Modify: `server/agent/prompt.md` and/or the tool descriptions in `server/agent/tools/*.py`, plus `tests/evals/cases.py` only if a case's check is wrong (ledger a ruling for that)
- Test: `tests/evals/test_live.py`

- [ ] **Step 1: Run each flaky case 3 times live** and keep the transcripts in the workspace: `uv run pytest tests/evals/test_live.py -k "q10 or q13 or q19" --count=3`. Use a loop if `pytest-repeat` is absent. Record each failure's reason in the ledger.
- [ ] **Step 2: Fix the cause** with the smallest change: a prompt rule, a tool description, or a missing tool argument. Do not change the expected answers unless the case itself is wrong.
- [ ] **Step 3: Run** the three cases 3 times, then the full live suite once. Expected: each of q10, q13 and q19 passes 3 of 3, and the full suite passes at least 19 of 20.
- [ ] **Step 4: Commit** `fix: stabilise evals q10 q13 q19`.

### Task 5: Docs and final checks

- [ ] Add a v1 addendum to `context/decisions.md`: category suggestions, the scheduler, and the type-rule ruling from T2. Update `AGENTS.md` commands (`ka suggest`).
- [ ] **Run** `uv run pytest -q`, `uv run ruff check .`, and `uv run python scripts/commit_guard.py`. Expected: all pass.
- [ ] **Commit** `docs: categories and scheduler`.
