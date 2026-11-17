# Ka build steps 1 to 3: design addendum (16 Nov 2026)

Adds to `Docs/Ka design .md` (the spec). Where the two differ, this file wins for steps 1 to 3.
It records only what the spec left open or what the real statement changed.

## Intent

Get the foundation working end to end on this machine: two git repos, validated data files, and a
Scotiabank chequing parser that turns a real PDF into reconciled, tagged rows. No agent, no model
calls, no UI in this pass. The owner must be able to explain every part afterwards.

## Goals

- Step 1: code repo and data repo exist, with the coding setup from the spec.
- Step 2: every YAML file in the spec's Data schemas loads through a Pydantic model.
- Step 3: `ka import <pdf>` parses the real statement, passes all checks, and writes rows after a
  yes at the prompt.

## Non-goals

- Tools, adapter, agent loop, memory, evals, onboarding (steps 4 to 8, planned later).
- UI of any kind. No `ui/` folder is created.
- Entertainer.
- Google Drive and Sheets. No Google code in this pass.
- Other banks, other account kinds, OCR.

## Anti-goals

- Personal data, real statements or secrets in the code repo.
- An LLM anywhere in the parser or tagging path.
- Float arithmetic on money.
- Rows written when any check fails.
- Remotes or pushes. Both repos stay local.

## Decisions made with the owner

| Topic | Decision |
|---|---|
| Repos | Local git only. Code repo is this folder (`Ka/`). Data repo is `~/Projects/ka-data`. |
| Evals | Code repo evals use a synthetic persona. Real-data expectations live in the data repo. (Applies from step 7.) |
| Real statement | The owner supplies the real PDF. It is read for layout only and never enters the code repo. |
| Scope | Component logic only. Plan covers steps 1 to 3. |
| Card and loan payments | Tagged `debt_payment`, excluded from spending, reported as their own line. |
| Accounts | The second chequing/savings account, the investment account, the credit card and the loan seen on the statement are all the owner's. `accounts.yaml` gains a `match` field. |
| E-transfers | Outgoing is spending with category `e_transfer`. Incoming is `income`. Single rows are relabelled later through chat. |

## Calls made by the builder (owner to check)

1. **Finance storage before Google.** The owner did not answer this one, so the default applies:
   a `FinanceStore` interface with a local CSV backend. Files:
   `~/Projects/ka-data/local/finance/statements.csv` and `transactions.csv`, with the exact
   columns of the spec's two sheet tabs. `local/` is gitignored, so finance stays out of git as the
   spec intends. A Google Sheets backend implements the same interface later.
2. **The spec file holds personal data** (employer names, account digits, real eval answers), and
   the spec says to copy it to `context/decisions.md` in the code repo. That would break the
   no-personal-data rule. The copy is redacted (synthetic names, no account digits). The original
   and this addendum's unredacted parts move to `~/Projects/ka-data/docs/`.
3. **The real statement moves** from `Ka/statements/` to `~/Projects/ka-data/local/statements/`
   in step 1.
4. **No pending queue yet.** It lives in SQLite, which arrives in step 6. In step 3, unknown
   merchants get an empty category and unknown type texts get a fallback tag; the import report
   lists both. Nothing is lost: they are found again later by empty category.
5. **Approval in step 3** is a yes or no prompt in the `ka import` command, since there is no chat
   yet. It shows row count, totals, check results, and the unknown merchants and types.
6. **Generic bank knowledge ships in code**: `server/finance/defaults/scotiabank_types.yaml`.
   The data repo's `rules/transaction_types.yaml` overrides or adds entries.
7. **ID counters**: `ids.yaml` in the data repo holds the next number per ID prefix, so a deleted
   record's ID is never reused.
8. **`other.yaml`** starts with one type: `project`.
9. **Denylist for the commit hook** is filled by the builder from the statement and the spec; the
   owner adds anything missing. If the denylist file is absent the hook warns and passes, so the public
   repo still works for someone without a data repo. If `config.yaml` itself is missing the hook
   blocks, so a fresh clone or worktree cannot commit without a denylist by accident.
10. **Account details not printed on the statement** (bank of the investment account, last4 of
    card and loan) are left empty or assumed and listed for the owner to correct.
11. Python 3.13, uv, ruff, pytest. Package name `ka-agent`. No licence file yet.

## Approaches

**Parsing the PDF**

| Approach | Trade-off |
|---|---|
| A. Word positions (chosen) | Each word comes with x and y. Columns are told apart by x range, rows by y. Survives merchant names that contain numbers; gives the withdrawn/deposited column for free. Slightly more code. |
| B. Text lines plus regex | Shorter. Breaks when a description contains an amount-like number (the real statement has such rows) and cannot see which amount column a number sat in. |
| C. `extract_table` | No ruling lines in this PDF, so table detection is guesswork. |

A is chosen because the real statement has descriptions with amount-like numbers and because the
column gives an independent check.

**Finance storage before Google**: CSV backend behind an interface (chosen) vs. mocks only (finance
tools could not run on real data until Google is set up) vs. SQLite (the spec keeps finance in a
sheet; CSV maps one to one onto the tabs).

## Step 1: repo setup

Code repo `Ka/`:

- `git init`, `pyproject.toml` (uv), ruff, pytest, `.gitignore` (`.env`, `config.yaml`, `*.pdf`
  outside `tests/fixtures`, `.DS_Store`).
- Folders: `server/{agent,finance,memory,integrations,store,api}`, `tests/` mirroring `server/`,
  `tests/evals/`, `tests/fixtures/`. Empty packages only where steps 1 to 3 do not fill them.
- `AGENTS.md`: Python conventions, uv commands, how to run tests, Ka rules (no LLM in the parser,
  money exact, list affected files and callers before editing, feature folder naming, feature
  flags, never load `interview.md`).
- `context/`: `index.md`, `conventions.md`, `decisions.md` (redacted spec plus this addendum),
  `flows/`.
- `.claude/agents/reviewer.md` and `.claude/skills/flow-docs/SKILL.md` as the spec describes.
- Pre-commit hook in `scripts/hooks/pre-commit`, enabled with `git config core.hooksPath`. Blocks:
  `.env` files, PDFs anywhere (tests build synthetic PDFs on the fly; compressed text would hide personal data from the scan), common secret patterns, and any string listed in an
  untracked denylist file (`~/Projects/ka-data/local/denylist.txt`: name, emails, account
  numbers, employer names). Has its own test.
- `config.example.yaml` (data repo path, flags, all default off) and a loader. `config.yaml` is
  gitignored.

Data repo `~/Projects/ka-data`: `git init`, `.gitignore` with `local/`, folders `rules/`, `docs/`,
`local/statements/`, `local/finance/`.

## Step 2: data files

- One Pydantic model module per file in the spec's Data schemas, plus `ids.yaml`.
- Schema change: `accounts.yaml` entries gain `match`, a list of strings looked for
  (case-insensitive, spaces ignored) in a transaction description.
- Loader in `server/integrations`: reads with ruamel.yaml, validates, reports the file and field on
  failure. Writing YAML is step 4 (`propose_change`), not here.
- Cross-file checks on load: highlight domain IDs exist, IDs unique, exactly one address marked
  current at most, category names in rules exist in `categories.yaml`.
- Synthetic sample data for a made-up person in `tests/fixtures/data/`.
- Real data repo gets valid skeleton files. Filled in now, from the statement and the owner's
  answers: `accounts.yaml` (five accounts), `categories.yaml` (starter list including
  `e_transfer`), and the e-transfer merchant rule. Everything else waits for onboarding.

## Step 3: parser

Pipeline, each stage a separate module in `server/finance`:

1. **Extract** (`parser`): pdfplumber words with `x_tolerance=1.5`. Reject the file with a clear
   error unless it is a Scotiabank chequing statement (header text check; the layout detector for
   other banks comes later).
2. **Summary**: page 1 gives account number, period start and end with year, opening balance,
   total withdrawals, total deposits, closing balance.
3. **Rows**: a row starts at a line with a date in the date column. Its amount is read from the
   withdrawn or deposited column, its balance from the balance column. Zero or one following line
   in the description column is its description. Opening and closing balance lines are not
   transactions. Anything outside the table's x range or between tables is ignored.
4. **Dates**: rows carry month and day only. The year is the one that places the date inside the
   statement period, which also handles a December to January statement.
5. **Direction and sign**: decided by the running balance, as the spec says. Amounts are `Decimal`,
   negative for money out.
6. **Checks** (`reconcile`), all must pass or nothing is written and the report names the check
   and the first failing row:
   1. each balance equals the previous balance plus the signed amount;
   2. sums of withdrawals and deposits equal the summary totals;
   3. opening plus deposits minus withdrawals equals closing;
   4. the amount's column agrees with the direction from the balance.
7. **Tagging** (`tagging`), first match wins:
   0. the row's type rule has `nets_against_original` (error correction, returned NSF): that
      rule's tag, so a returned loan or card payment is never counted as borrowing;
   1. description matches an own account's `match`: kind chequing, savings or investment gives
      `own_transfer`; kind credit or loan gives `debt_payment` for money out and `borrowing` for
      money in;
   2. type text matches a transaction type rule (code defaults, then data repo overrides);
   3. fallback: money out is `purchase`, money in is `income`, and the type is reported as unknown.
   Category comes from the first merchant rule whose `match` is in the description; none means an
   empty category, reported as unknown.
8. **Netting**: a row whose type rule has `nets_against_original` (error correction, returned NSF)
   is linked to the nearest earlier unlinked row with the same description and amount within 60
   days, searching this statement and rows already stored. The link is one-way: only the
   correcting row carries `linked_id`, stored rows are never rewritten. No match leaves `linked_id` empty and is
   reported. Own-transfer rows keep `linked_id` empty until the other account has a parser.
9. **Write**: `statement_id` is `<bank>-<kind>-<last4>-<period end YYYY-MM>`. Row `id` is
   `statement_id` plus a three-digit row number. The account ID comes from `accounts.yaml`; an
   unknown account number stops the import with a message to add it. A `statement_id` already in
   the store is skipped. Rows go through `FinanceStore` after a yes.

Command: `uv run ka import <path>` and `uv run ka statements` (lists PDFs in the statements folder
and which are imported).

Tests:

- Synthetic PDFs built by a fixture script (reportlab, dev dependency) that places text at the real
  column positions with fake people, merchants and amounts. Cases: normal, row without
  description, negative balance, amount with comma, description containing an amount-like number,
  error correction, returned NSF, loan deposit, own transfer, December to January period, each of
  the four checks failing, duplicate import, wrong bank.
- One opt-in test runs the real statement when `KA_REAL_STATEMENT` points to it; skipped otherwise.
  It asserts only that the four checks pass and the row count is stable.

## Done for each step

Tests pass, ruff clean, the flow doc is written with the flow-docs skill (step 3: the
import-statement flow, noting that Drive, model suggestions and chat approval come later), and one
local commit per logical change with a conventional prefix. Evals do not apply before step 6.

## Left to the builder

Module and function names, exact x ranges for columns (measured from the real PDF, stored as named
constants), the starter category list, hook regexes, the redaction wording.
