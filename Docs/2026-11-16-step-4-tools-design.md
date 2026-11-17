# Ka build step 4: tools (design addendum, 16 Nov 2026)

Adds to `Docs/2026-11-16-steps-1-3-design.md` and the spec in `context/decisions.md`. Where they
differ, this file wins for step 4. It records only what the spec left open.

## Intent

The agent in step 6 must be able to read the owner's data and propose changes without ever
touching files or running commands itself. Step 4 builds those tools as plain Python functions
behind a registry, tested without any model.

## Goals

- A registry where each tool has a name, description, Pydantic args model, function, a READ or
  WRITE label and an approval flag. Args are validated before the function runs.
- Ten tools: `get_profile`, `get_jobs`, `search`, `finance_summary`, `search_transactions`,
  `sum_transactions`, `list_statements` (READ); `propose_change`, `import_statement` (WRITE, need
  approval); `remember` (WRITE, saves immediately).
- Money leaves tools as strings, so the model never sees a float.

## Non-goals

- `search_conversations` (needs the SQLite store, step 6). Inferred-memory pending queue (step 7).
- The approval prompt and the agent loop (step 6). Tools only expose the seam.
- Editing `categories.yaml`, `rules/transaction_types.yaml` and `ids.yaml` through
  `propose_change`. Those arrive with the pending queue.
- Google Drive for statements. Local folder behind an interface for now.
- MCP wrapping.

## Anti-goals

- A tool that writes a file, runs a shell command or commits before approval (except `remember`,
  which the spec says saves immediately).
- The model producing raw YAML or file paths.
- A dirty or half-written data repo after a declined or failed change.

## Decisions made with the owner

| Topic | Decision |
|---|---|
| Scope | Ten tools now. `search_conversations` and the inferred-memory queue wait. |
| Write contract | An approval-needed tool returns a `PendingWrite(summary, diff, apply)`. Nothing is written until the loop calls `apply` after a yes. |
| Diff | Computed in memory from the patched YAML text (unified diff). A "no" leaves nothing to clean up. A target file with uncommitted edits is refused. |
| `propose_change` shape | Structured patch: target, operation (`add`, `update`, `retire`, `delete`), key, parent, fields. Code applies it, then validates the whole repo. |
| `finance_summary` | Spending = purchase, fee, refund and nsf_return rows, corrections netted. Own transfers and borrowing excluded. Debt payments, income and spending are separate lines. Empty category shows as `uncategorised`. A period with no rows returns `has_data: false` and no totals. |

## Calls made by the builder (owner to check)

1. **Tool context.** Tools receive a `ToolContext` (config, finance store, a `today` function).
   Data is reloaded from disk on each access so a committed change is visible at once.
2. **Patch targets**: `profile`, `education`, `domain`, `job`, `highlight`, `guardrail`, `memory`,
   `account`, `merchant_rule`, `other_record`. A job is addressed as `Company|YYYY-MM`. A highlight
   is added with `parent` set to its job key.
3. **Ids on add** come from `ids.yaml` counters, bumped in the same change. Widths: E 2, D 2, H 3,
   G 2, M 4, A 2, R 3, O 3.
4. **`retire`** works only where the schema has the flag (highlight `retired`, memory `status`);
   any other target gets an error saying to use `delete`.
5. **YAML writing** uses ruamel.yaml round-trip mode so comments, order and flow style survive. A
   test proves a no-op round trip is byte-identical on the fixture files; if it is not, diffs would
   be noisy and the plan stops for a ruling.
6. **Concurrency.** One lock file (`.ka.lock`, git-ignored) around apply. Apply re-reads the file
   and refuses if it changed since the proposal.
7. **Commit.** Only the touched files are staged. Message `data: <op> <target> <key>`. Commit goes
   straight to `main`, as the spec says.
8. **`remember`** writes a `fact`, `preference` or `rule` entry with empty `source`, dated today.
9. **`import_statement`** takes a file name from the statements folder only (no paths, `.pdf`
   only). Failed checks or an already imported statement are errors, not approvals.
10. **`search`** is a case-insensitive substring match over every record's text, returning file,
    id and a short snippet.
11. **Folded-in minors from the final review**: corrections link only within the same account;
    account and merchant `match` strings need at least 4 non-space characters.
12. **`remember` commits** through the same plan and apply path as any approved write, so memory.yaml is
    never left dirty. It obeys the dirty-file refusal.
13. **Keys.** Every id-bearing target is addressed by its id, including `merchant_rule` and
    `other_record`. A job is addressed by the exact stored `Company|start` string, and `update` may
    not change `company` or `start` (delete and re-add instead). `propose_change` cannot add an
    `other` type or edit `ids.yaml` directly; an `other_record` with an unapproved type fails
    validation.
14. **`import_statement`** shows row count, totals and the first rows as its "diff"; apply writes
    the finance CSV only. Nothing is committed, because `local/` is git-ignored.
15. **`.ka.lock`** is added to the private data repo's `.gitignore` and committed there by the
    builder.
16. **Real data check.** The folded-in minimum length is satisfied by the real accounts and rule;
    `ka check` on the real repo is a plan step. No real transactions are stored yet, so no migration.
17. **`sum_transactions`** takes row ids, returns the exact signed total and lists unknown ids in
    `missing` (partial sum, not an error). `finance_summary` takes an inclusive `start` and `end`.

## Approaches

**Showing the diff for approval**

| Approach | Trade-off |
|---|---|
| A. In-memory diff, write on yes (chosen) | No dirty tree on a "no", nothing to roll back, can be tested without git. Needs a small apply step. |
| B. Write to working tree, show `git diff`, `git checkout` on no | Matches the spec wording literally, but a crash leaves a dirty data repo and other writers could collide. |

**Patch format**: structured patch (chosen) vs. letting the model send a YAML fragment. The
fragment is shorter to describe but lets the model write arbitrary text into files and makes
validation and id assignment its problem.

## Done

Tests pass, ruff clean, tools flow doc written, one commit per logical change. Evals still do not
apply (step 6).
