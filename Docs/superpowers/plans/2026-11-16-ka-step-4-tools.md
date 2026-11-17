# Ka Step 4 (Tools) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ten agent tools behind a validated registry, with an approval seam for writes, tested without any model.

**Architecture:** `server/agent/tools/` holds a decorator registry plus tool modules. Pure finance maths lives in `server/finance/queries.py`. Data repo edits go through one writer module (`server/integrations/data_repo/writer.py`): patch, validate whole repo, in-memory diff, lock, commit. Approval-needed tools return a `PendingWrite`; step 6's loop shows it and calls `apply`.

**Tech Stack:** Python 3.13, Pydantic v2, ruamel.yaml (round-trip), git via `subprocess`, difflib, fcntl.

**Spec:** `Docs/2026-11-16-step-4-tools-design.md` (wins), `Docs/2026-11-16-steps-1-3-design.md`, `context/decisions.md`. Built on the finished steps 1 to 3 code.

## Global Constraints

- Tools are plain Python functions; the model never writes YAML, file paths or shell commands. Git runs only through `subprocess` inside `writer.py`.
- Money is `Decimal`; tool outputs carry Decimals as strings (`"-4.50"`). No `float`.
- No LLM call anywhere in this plan. No Google code. No new dependency.
- All Pydantic models use `extra="forbid"` (subclass `KaModel` from `server.integrations.data_repo.schemas.common`).
- No personal data, real statement or secret in the code repo. Test fixtures use the invented persona in `tests/fixtures/data`.
- Data repo commits go straight to `main`, message `data: <op> <target> <key>`; only touched files are staged.
- Tests stay minimal: one test per risky behaviour listed in the task, not per function. Run `uv run pytest` and `uv run ruff check .` before each commit.
- The commit hook needs a review go-ahead for each commit: batch commits at the ends of Tasks 3, 5 and 6, as in steps 1 to 3.
- Commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. `finance_summary` for a period with no rows returns `has_data: false` and no totals, not zeros. (Task 3)
2. `search_transactions("tim hortons")` finds `TimHortons#22` (case and spaces); `sum_transactions` adds exact decimals. (Task 3)
3. A `propose_change` that fails validation leaves every file and the git log untouched; a target file with uncommitted edits is refused. (Task 4)
4. A second proposal on the same file applied after the first is refused ("changed since proposal"). (Task 4)
5. `import_statement` with `../x.pdf`, a non-PDF name, an already imported file or failing checks raises `ToolError` and writes nothing. (Task 5)

---

## File Structure

```
server/agent/tools/__init__.py        imports tool modules so decorators run; exports REGISTRY, run_tool
server/agent/tools/registry.py        Tool, PendingWrite, ToolError, ToolContext, @tool, run_tool
server/agent/tools/data_tools.py      get_profile, get_jobs, search
server/agent/tools/finance_tools.py   finance_summary, search_transactions, sum_transactions, list_statements
server/agent/tools/write_tools.py     propose_change, remember, import_statement
server/finance/queries.py             summarise, find_transactions, sum_rows
server/finance/statements.py          list_statement_files (shared by CLI and tool)
server/integrations/data_repo/writer.py   Patch, plan_change, apply_change
tests/agent/tools/test_*.py           mirror the modules
```

---

### Task 1: Registry, context, PendingWrite

**Files:**
- Create: `server/agent/tools/__init__.py`, `server/agent/tools/registry.py`, `tests/agent/__init__.py`, `tests/agent/tools/__init__.py`
- Test: `tests/agent/tools/test_registry.py`

**Interfaces:**
- Produces:

```python
class ToolError(Exception): ...            # message goes back to the model as the tool result

@dataclass
class PendingWrite:
    summary: str
    diff: str
    apply: Callable[[], str]               # performs the write, returns a one-line result

@dataclass
class ToolContext:
    config: Config
    store: FinanceStore
    today: Callable[[], date] = date.today
    @property
    def data(self) -> KaData: ...          # load_data(config.data_repo) on every access

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[KaModel]
    fn: Callable[[Any, ToolContext], Any]
    mode: Literal["READ", "WRITE"]
    approval: bool                         # True: fn returns PendingWrite

REGISTRY: dict[str, Tool]
def tool(name: str, description: str, args_model: type[KaModel],
         mode: Literal["READ", "WRITE"] = "READ", approval: bool = False): ...   # decorator
def run_tool(name: str, raw_args: dict, ctx: ToolContext) -> dict | PendingWrite
def to_json(value: Any) -> Any             # Pydantic -> dump(mode="json"); Decimal -> str; date -> iso; recurses dict/list
```

`run_tool`: unknown name raises `ToolError(f"unknown tool: {name}")`; `ValidationError` becomes `ToolError` listing each `field: message`; for `approval=True` tools the `PendingWrite` is returned as is; otherwise the function's result passes through `to_json`. Registering the same name twice raises `ValueError`. `DataRepoError` from `ctx.data` is not caught here.

- [ ] **Step 1: Write failing test** `test_registry.py::test_validates_args_serialises_money_and_rejects_unknown`: register a throwaway tool in a fresh `REGISTRY` (monkeypatch the dict) taking `Args(amount: Decimal)` and returning `{"total": Decimal("0.10") + Decimal("0.20")}`; assert `run_tool(...)["total"] == "0.30"`; bad args (`{"amount": "x"}`) raise `ToolError` whose message contains `amount`; unknown name raises `ToolError`.
- [ ] **Step 2:** Run `uv run pytest tests/agent -v`. Expected: FAIL, module missing.
- [ ] **Step 3:** Implement `registry.py`. `__init__.py` exports `REGISTRY`, `run_tool`, `ToolError`, `PendingWrite`, `ToolContext` (tool modules are imported by Task 2 onward).
- [ ] **Step 4:** Run tests and ruff. Expected: pass. Do not commit yet (batched in Task 3).

---

### Task 2: Data read tools

**Files:**
- Create: `server/agent/tools/data_tools.py`; modify `server/agent/tools/__init__.py` (import the module)
- Test: `tests/agent/tools/test_data_tools.py`

**Interfaces:**
- Consumes: Task 1 registry; `KaData`.
- Produces (registered names, args, result):
  - `get_profile` (no args) returns the `Profile` dump.
  - `get_jobs(include_retired: bool = False)` returns `{"domains": [...], "jobs": [... with highlights]}`; retired highlights omitted unless asked.
  - `search(query: str, limit: int = 20)` returns `{"hits": [{"file": str, "id": str, "snippet": str}], "truncated": bool}`. Records searched: profile (id `profile`), each education entry, domain, job (id `Company|YYYY-MM`), highlight, guardrail, memory entry, account, merchant rule, other record. Match is case-insensitive substring over the record's joined string values; snippet is the first 160 characters of that text. Empty query raises `ToolError`.
- Add a ctx fixture in `tests/agent/tools/conftest.py`: copies `tests/fixtures/data` into `tmp_path/repo` (git-initialised and committed, used from Task 4 on), builds `Config(data_repo=repo)` and a `CsvFinanceStore(tmp_path/"fin")`, returns `ToolContext`.

- [ ] **Step 1: Write failing tests**: `test_search_finds_record_by_id_and_text` (`search("react")` hits `H-003` in `jobs.yaml`; `search("CORNER")` hits merchant rule `R-001`); `test_get_jobs_hides_retired_highlights_by_default` (H-004 absent, present with `include_retired=True`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the three tools; a private `_records(data) -> list[tuple[str, str, str]]` flattens records.
- [ ] **Step 4:** Run tests. Expected: pass.

---

### Task 3: Finance read tools and statements helper

**Files:**
- Create: `server/finance/queries.py`, `server/finance/statements.py`, `server/agent/tools/finance_tools.py`; modify `server/cli.py` (`_statements` uses the helper), `server/agent/tools/__init__.py`
- Test: `tests/finance/test_queries.py`, `tests/agent/tools/test_finance_tools.py`

**Interfaces:**
- Produces in `queries.py`:

```python
SPENDING_TAGS = {"purchase", "fee", "refund", "nsf_return"}

class Summary(KaModel):
    start: date; end: date
    has_data: bool
    rows: int                              # rows in the period, all tags
    data_from: date | None; data_to: date | None   # first and last date found in the period
    spending: Decimal | None               # positive number; None when no data
    by_category: dict[str, Decimal]        # spending per category, empty category -> "uncategorised"
    income: Decimal | None
    debt_payments: Decimal | None          # positive number
    borrowing: Decimal | None

def summarise(rows: list[Transaction], start: date, end: date) -> Summary
def find_transactions(rows, query: str = "", start=None, end=None, tag=None, category=None,
                      min_amount: Decimal | None = None, max_amount: Decimal | None = None) -> list[Transaction]
def sum_rows(rows: list[Transaction], ids: list[str]) -> tuple[Decimal, list[str]]   # (signed total, missing ids)
```

  Rules: period is inclusive both ends. `spending = -sum(amount)` over `SPENDING_TAGS`. `own_transfer` rows are excluded from every total. `has_data` false means every Decimal field is `None` and `by_category` is `{}`. `find_transactions` matches `query` against `norm(description)` and `norm(type)` (import `norm` from `server.finance.tagging`), `min_amount`/`max_amount` compare `abs(amount)`; rows return sorted by `(date, id)`.
- In `statements.py`: `StatementFile(name: str, imported: bool)` and `list_statement_files(config: Config, store: FinanceStore) -> list[StatementFile]` (sorted `*.pdf` in `config.statements_dir`; `imported` when the name is a stored `file_name`; missing folder gives `[]`).
- Tools: `finance_summary(start: date, end: date)`; `search_transactions(query: str = "", start: date | None, end: date | None, tag: str | None, category: str | None, min_amount: Decimal | None, max_amount: Decimal | None, limit: int = 50)` returns `{"rows": [...], "total_matches": int, "truncated": bool}`; `sum_transactions(ids: list[str])` returns `{"total": "-12.34", "count": int, "missing": [...]}`; `list_statements` (no args) returns `{"files": [{"name", "imported"}]}`.

- [ ] **Step 1: Write failing tests**:
  - `test_queries.py::test_summary_nets_corrections_excludes_transfers_and_reports_no_data`: rows: purchase -10.00 (dining), refund +10.00, own_transfer -50.00, income +100.00, debt_payment -30.00, purchase -4.50 with empty category. Assert `spending == Decimal("4.50")`, `by_category == {"uncategorised": Decimal("4.50")}`, `income == Decimal("100.00")`, `debt_payments == Decimal("30.00")`; a period containing no rows gives `has_data is False` and `spending is None`.
  - `test_queries.py::test_search_ignores_case_and_spaces_and_sum_is_exact`: row `TimHortons#22` found by `"tim hortons"` and `"TIMHORTONS"`; `sum_rows` of `-0.10`, `-0.20` gives `Decimal("-0.30")` and reports an unknown id in `missing`.
  - `test_finance_tools.py::test_tools_return_strings_and_limit_rows`: seed the ctx store with 3 rows via `add_import`; `run_tool("search_transactions", {"limit": 2})` returns 2 rows, `truncated` true, `total_matches` 3, amounts as strings; `run_tool("list_statements", {})` marks an imported file `imported: true` and a new PDF `false`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `queries.py`, `statements.py`, the four tools; point `cli._statements` at `list_statement_files` (same printed format).
- [ ] **Step 4:** Run `uv run pytest -q && uv run ruff check .`. Expected: all pass, including the existing CLI test.
- [ ] **Step 5: Commit** (Tasks 1 to 3 in one commit; get review go-ahead first): `feat: add tool registry and read tools`.

---

### Task 4: Data repo writer

**Files:**
- Create: `server/integrations/data_repo/writer.py`
- Modify: `~/Projects/ka-data/.gitignore` (add `.ka.lock`), `tests/agent/tools/conftest.py` (fixture already git-initialises)
- Test: `tests/integrations/data_repo/test_writer.py`

**Interfaces:**
- Consumes: `load_data`, `DataRepoError`, `FILES` from `loader.py`.
- Produces:

```python
Target = Literal["profile", "education", "domain", "job", "highlight", "guardrail",
                 "memory", "account", "merchant_rule", "other_record"]

class Patch(KaModel):
    target: Target
    op: Literal["add", "update", "retire", "delete"]
    key: str | None = None        # record id; job key "Company|YYYY-MM"; None for profile or add
    parent: str | None = None     # job key, required when adding a highlight
    fields: dict[str, Any] = {}

@dataclass
class ChangePlan:
    files: dict[str, tuple[str, str]]      # relative path -> (old text, new text)
    diff: str                              # unified diff of all changed files
    message: str                           # commit message

class ChangeError(Exception): ...         # bad patch, validation failure, dirty file

def plan_change(root: Path, patch: Patch) -> ChangePlan
def apply_change(root: Path, plan: ChangePlan) -> str    # returns commit hash (short)
```

Target table (file, list path, key field): `education` (`education.yaml`, `entries`, `id`), `domain` (`jobs.yaml`, `domains`, `id`), `job` (`jobs.yaml`, `jobs`, key `company|start`), `highlight` (`jobs.yaml`, `jobs[*].highlights`, `id`), `guardrail` (`guardrails.yaml`, `rules`, `id`), `memory` (`memory.yaml`, `entries`, `id`), `account` (`accounts.yaml`, `accounts`, `id`), `merchant_rule` (`rules/merchants.yaml`, `rules`, `id`), `other_record` (`other.yaml`, `records`, `id`), `profile` (`profile.yaml`, the root mapping, `update` only).

Behaviour:
- `add`: new id = `f"{prefix}-{n:0{width}d}"` from `ids.yaml` `next[prefix]` (prefixes and widths: E 2, D 2, H 3, G 2, M 4, A 2, R 3, O 3); `next` is incremented in the same plan, so `ids.yaml` appears in `files`. `job` has no id (key from `company` and `start` fields). `highlight` add needs `parent`. `fields` must not contain `id`.
- `update`: merges `fields` into the record (replaces list values whole). `retire`: sets `retired: true` (highlight) or `status: retired` (memory); any other target raises `ChangeError("cannot retire <target>; use delete")`. `delete`: removes the record.
- Unknown key, duplicate job key or missing parent raise `ChangeError` naming it. `update` on a `job` whose `fields` include `company` or `start` raises `ChangeError("company and start identify a job; delete and re-add")`.
- Reading and writing use `ruamel.yaml` round-trip (`YAML()` with `preserve_quotes=True`, `width=4096`); only files that change appear in `files`.
- Validation: write all new texts over a temp copy of the repo and call `load_data(copy)`; a `DataRepoError` becomes `ChangeError(str(error))`. The real repo is untouched.
- `diff`: `difflib.unified_diff` per changed file, headers `a/<path>` and `b/<path>`.
- `plan_change` raises `ChangeError("<path> has uncommitted changes")` when `git status --porcelain -- <path>` is non-empty for any file it changes.
- `apply_change`: take an exclusive `fcntl.flock` on `<root>/.ka.lock`; re-read every file in `plan.files` and raise `ChangeError("<path> changed since proposal")` if the text differs from the plan's old text; re-run the dirty check; write; `git add -- <paths>`; `git commit -m <message>`; return `git rev-parse --short HEAD`. On any git failure raise `ChangeError` with git's stderr first line and restore the old texts.

- [ ] **Step 1: Write failing tests** (use the git-initialised repo copy; add a helper to commit all fixtures once):
  - `test_noop_roundtrip_is_byte_identical`: for every YAML file under `tests/fixtures/data`, ruamel load then dump equals the original text. If this fails, STOP: ledger a ruling (adjust fixtures to the dumper's style, or normalise on first write) before continuing.
  - `test_add_highlight_assigns_next_id_validates_and_commits`: `Patch(target="highlight", op="add", parent="Acme Widgets|2022-03", fields={"text": "Shipped X", "domains": ["D-01"]})`; plan diff contains `H-005` and `next:` change in `ids.yaml`; after `apply_change` a new commit exists, `git status` is clean, `load_data` shows the highlight, and `ids.yaml` says `H: 6`.
  - `test_invalid_patch_changes_nothing`: highlight add with `domains: ["D-99"]` raises `ChangeError` containing `D-99`; `git log` length and file texts unchanged.
  - `test_stale_plan_and_dirty_file_are_refused`: plan two updates to the same record; apply the first; applying the second raises `ChangeError` containing `changed since proposal`. Separately, after editing `guardrails.yaml` by hand, `plan_change` on a guardrail raises `ChangeError` containing `uncommitted`.
- [ ] **Step 2:** Run `uv run pytest tests/integrations/data_repo/test_writer.py -v`. Expected: FAIL (import).
- [ ] **Step 3:** Implement `writer.py`. Git calls go through one private `_git(root, *args) -> str` using `subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)`.
- [ ] **Step 4:** Run tests. Expected: pass. Add `.ka.lock` to the data repo `.gitignore` and commit it there (`git -C ~/Projects/ka-data commit -m "chore: ignore lock file"`). Code repo commit comes with Task 5.

---

### Task 5: Write tools

**Files:**
- Create: `server/agent/tools/write_tools.py`; modify `server/agent/tools/__init__.py`
- Test: `tests/agent/tools/test_write_tools.py`

**Interfaces:**
- Consumes: Task 1 registry; Task 4 `Patch`, `plan_change`, `apply_change`, `ChangeError`; `prepare_import`, `commit_import`, `ImportFailed`, `StatementFormatError`.
- Produces:
  - `propose_change(args: Patch)` registered `WRITE`, `approval=True`. Returns `PendingWrite(summary=plan.message, diff=plan.diff, apply=lambda: f"committed {apply_change(root, plan)}")`. `ChangeError` becomes `ToolError`.
  - `remember(text: str, type: Literal["fact","preference","rule"] = "fact")` registered `WRITE`, `approval=False`. Commits like any other write; a dirty `memory.yaml` raises `ToolError`. Builds a memory `add` patch (`status: active`, `created` and `updated` = `ctx.today().isoformat()`, `source` omitted), plans and applies immediately, returns `{"id": "M-0002", "commit": "<hash>"}`.
  - `import_statement(file_name: str)` registered `WRITE`, `approval=True`. Rejects names containing `/`, `\`, `..` or not ending `.pdf` with `ToolError`. Calls `prepare_import(statements_dir / file_name, ctx.data, ctx.store)`; failing checks raise `ToolError` listing `check row: message`; `already_imported` raises `ToolError(f"already imported: {id}")`; otherwise returns `PendingWrite(summary=f"{n} rows, withdrawals {w}, deposits {d}, checks passed" plus unknown types or merchants when present, diff=same table of the first 10 rows as text, apply=lambda: f"written {commit_import(preview, ctx.store)} rows")`. `ImportFailed` and `StatementFormatError` become `ToolError`.

- [ ] **Step 1: Write failing tests**:
  - `test_propose_change_returns_pending_write_and_writes_only_on_apply`: update `A-01` label via `run_tool("propose_change", {...}, ctx)`; result is `PendingWrite`, `git log` count unchanged and file text unchanged; after `result.apply()` the label changed and a commit exists.
  - `test_remember_saves_immediately`: `run_tool("remember", {"text": "Prefers remote roles", "type": "preference"}, ctx)` returns an id `M-0002`; memory file contains it; commit exists; the fixture repo still loads.
  - `test_import_statement_approval_and_refusals`: build a synthetic PDF with `build_statement` inside `ctx.config.statements_dir`; `run_tool("import_statement", {"file_name": "s.pdf"}, ctx)` returns a `PendingWrite` whose summary mentions `2 rows`; the store is empty until `apply()`, then holds 2 rows; a second call raises `ToolError` containing `already imported`; `"../s.pdf"` and `"notes.txt"` raise `ToolError`; a PDF built with `closing_balance` override raises `ToolError` containing `opening_closing`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the three tools; `remember` reuses `plan_change` and `apply_change` (no second write path).
- [ ] **Step 4:** Run `uv run pytest -q && uv run ruff check .`. Expected: all pass.
- [ ] **Step 5: Commit** Tasks 4 and 5 (review go-ahead first): `feat: add data repo writer and write tools`.

---

### Task 6: Folded-in minors, tools flow doc

**Files:**
- Modify: `server/finance/tagging.py` (`_find_original`), `server/integrations/data_repo/schemas/accounts.py`, `server/integrations/data_repo/schemas/rules.py`, `context/index.md`
- Create: `context/flows/tools.md`, `context/flows/tools.interview.md`
- Test: `tests/finance/test_tagging.py`, `tests/integrations/data_repo/test_schemas.py`

**Interfaces:**
- Consumes: `Transaction.account`; `norm` from `tagging.py`.
- Produces: corrections only match originals with the same `account`; `Account.match` entries and `MerchantRule.match` must have `len(norm(value)) >= 4` (validator raising `ValueError`).

- [ ] **Step 1: Write failing tests**: in `test_tagging.py` add `test_corrections_do_not_link_across_accounts` (existing charge with `account="A-02"`, correction tagged for `A-01`: `linked_id == ""` and the id is in `unlinked`); in `test_schemas.py` extend the rejection test: `Account(..., match=["12"])` and a merchant rule with `match="ab"` raise `ValidationError`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement both changes. Run the real data repo check: `uv run ka check`. Expected: `ok: 11 files` (real accounts and rule already satisfy the minimum).
- [ ] **Step 4:** Write `context/flows/tools.md` with the flow-docs skill: 3-sentence summary, Mermaid diagram (model request, `run_tool`, validation, READ result or `PendingWrite`, approval, `apply_change`, commit), one worked example tracing `propose_change` on a highlight with file and function names, failure cases (validation, dirty file, stale plan, path traversal), "why this way" notes (in-memory diff over working-tree diff; structured patch over YAML fragment; approval flag vs separate tool), and a "not yet" note (conversations search, pending queue, loop, Drive). Interview questions in `tools.interview.md`. Add the flow and its source files to `context/index.md`.
- [ ] **Step 5:** Run the full suite and ruff; `git add -A && uv run python -m scripts.commit_guard` (expected exit 0). Commit (review go-ahead first): `feat: link corrections per account, validate match length, document tools flow`.

---

## Done when

- `uv run pytest` and `uv run ruff check .` pass; `uv run ka check` prints `ok: 11 files`.
- `run_tool` serves all ten tools; none of them writes without `apply` except `remember`.
- A declined or failed `propose_change` leaves the data repo byte-identical and its git log unchanged.
- `context/flows/tools.md` exists and every file and function name in it exists in the code.
