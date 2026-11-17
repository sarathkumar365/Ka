# Ka v1: Private-Data Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once a conversation has touched finance data, every later model call in that conversation goes to a private model chain (today, an OpenRouter zero-data-retention provider; later, Ollama first), and never back to the default model.

**Architecture:**
- Tools carry a `private` mark. When a private tool runs in a turn, the loop marks the conversation private in SQLite and swaps to the private adapter for the rest of that turn and for every later turn.
- The private adapter is an ordered fallback chain built from the top-level `private_models` list. Ollama later becomes config only: one more entry at the head of the list.
- A failed chain never falls back to the default model.

**Tech Stack:** Existing `OpenAICompatAdapter` and the OpenRouter `provider` request options (`zdr: true`, `data_collection: "deny"`), SQLite, pytest.

**Spec:** `context/decisions.md`, the "Models" line: private data such as finance goes to a local model first, then to an OpenRouter provider with no or low data retention. The owner's call on 2026-11-17: zero-data-retention via OpenRouter now, with Ollama added later.

## Global Constraints

- Private tools: `get_transactions`, `spending_summary`, `finance_coverage`, `list_statements`, `get_accounts`, and every tool whose result contains amounts. The builder lists the final set in the flow doc.
- The first user question of a conversation goes to the default model, because nothing private is known yet. The question text is the owner's own words, so this is accepted.
- No fallback from the private chain to `models.default`. If the whole chain fails, the answer is the error `private model unavailable: <reason>`.
- Memory extraction for a private conversation uses the private chain.
- Category and type suggestions (`server/finance/suggest.py`, called from `ka import` and `ka suggest`) use the private chain: merchant texts are finance data.
- With `private_models` empty and the flag on, `ka serve` refuses to start, and `ka check` states the reason.
- Flag `private_routing`, default off. When it is off, behaviour is unchanged.
- Commits: commit guard; touch `.claude/.reviewed` only after a yes; no trailers; noreply author.

## Review Focus

1. A private tool runs in the middle of a turn. The very next model call in the same turn uses the private adapter, not only the next turn (T2 test).
2. A private conversation is reopened in a new browser tab or after a restart. It is still routed private, because the state is in the DB and not in memory (T2 test).
3. The private chain is down. The turn ends with the error, and the default adapter receives zero calls (T2 test).
4. OpenRouter ignores the options without an error. The request body is checked in a test, so a dropped option fails CI (T1 test).
5. A tool result is long and is retried after a timeout. The retry goes to the same chain entry and not to the default model (covered by the T1 chain test).

---

### Task 1: Config and fallback chain

**Files:**
- Modify: `server/config.py`, `server/agent/adapters/openai_compat.py`, `server/agent/adapters/__init__.py`, `config.example.yaml`
- Create: `server/agent/adapters/chain.py`
- Test: `tests/agent/test_adapters.py`

**Interfaces:**
- Produces:
  - `ModelConfig.zdr: bool = False`. When true and the provider is `openrouter`, `complete` sends `extra_body={"provider": {"zdr": True, "data_collection": "deny"}}`.
  - `Config.private_models: list[ModelConfig] = []` (top-level key).
  - `ChainAdapter(adapters: list[Adapter])` implements `Adapter`. It tries each adapter in order on `AdapterError` and raises `AdapterError("private model unavailable: <last reason>")` when all fail.
  - `build_private_adapter(cfg: Config, env=os.environ) -> ChainAdapter`.

- [ ] **Step 1: Write the failing tests:**
  - `test_zdr_sends_provider_options`: patch the openai client and assert that `extra_body` equals the dict above.
  - `test_chain_falls_through_then_fails`: with `[failing, ok]`, the result comes from `ok`. With `[failing, failing]`, it raises an error whose message contains `private model unavailable`.
- [ ] **Step 2: Run** `uv run pytest tests/agent/test_adapters.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code. In `config.example.yaml`, add the following, with a comment that an Ollama entry can go first later:
  ```yaml
  private_models:
    - {provider: openrouter, model: "set-me", zdr: true}
  ```
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: private model chain with zero-data-retention option`.

### Task 2: Route private conversations in the loop

**Files:**
- Modify: `server/agent/tools/registry.py` (add `private: bool = False` to the tool entry), `server/agent/tools/finance_tools.py`, `server/agent/loop.py`, `server/store/db.py` (new column `conversations.private integer not null default 0`, added in `SCHEMA` and by `alter table` when the column is missing), `server/api/chat.py`, `server/chat.py`, `server/memory/extract.py`, `server/scheduler.py`
- Test: `tests/agent/test_loop.py`

**Interfaces:**
- Consumes: T1 `ChainAdapter`.
- Produces:
  - `Db.is_private(conv_id) -> bool` and `Db.mark_private(conv_id) -> None`.
  - `run_turn(..., adapter: Adapter, private_adapter: Adapter | None = None)`. At the start of the turn it uses `private_adapter` when `db.is_private(conv_id)`. After any tool with `private=True` runs, it calls `mark_private` and uses `private_adapter` for the rest of the turn. When `private_adapter` is None, behaviour is unchanged.
  - `create_app(cfg, adapter_factory, private_factory: Callable[[], Adapter] | None = None, ...)`.
  - `extract_memories(..., private_adapter: Adapter | None = None)`. Messages from private conversations go only to `private_adapter`. When it is None, they are skipped and counted in an activity line.
  - Settings `/api/settings` adds `private_models` (provider and model names only) and `private_routing`.

- [ ] **Step 1: Write the failing tests**, using `FakeAdapter` instances that record their calls:
  - `test_switches_within_turn`: the default model asks for `spending_summary`. The second model call is on the private adapter, and the default has exactly 1 call.
  - `test_private_persists_across_turns`: a new `run_turn` on the same conversation (a new `Db` handle on the same file) calls the private adapter first.
  - `test_chain_down_never_uses_default`: the private adapter raises. The answer contains `private model unavailable`, and the default call count is still 1.
- [ ] **Step 2: Run** `uv run pytest tests/agent/test_loop.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code. The terminal `ka chat` builds both adapters when the flag is on.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Then run the live finance evals with the private chain configured: `uv run pytest tests/evals/test_live.py -k finance`. Expected: pass, and the finance evals are no worse than before.
- [ ] **Step 5: Commit** `feat: route finance conversations to the private model chain`. Update the `context/flows/chat.md` and `settings.md` docs (`flow-docs` skill), and add a decisions addendum: ZDR now, Ollama later as config.
