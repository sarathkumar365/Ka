# Onboarding intake: design

Status: draft for owner approval. Builds on `context/decisions.md` (sections Onboarding, Memory, UI addendum).

## Intent and why

The owner's data files are nearly empty (profile has a name only, no jobs, no highlights, no domains), so Ka answers "no job records" to career questions. Typing everything through chat is slow. Intake reads the owner's documents and pasted AI-memory exports, proposes structured records, and lets the owner approve them before anything touches the YAML files. Success: a resume goes in, and a few minutes later the owner has reviewed it job by job and the data repo holds validated, committed records that the agent can cite.

## Goals

- Read a resume (and other documents) in most common formats: PDF, DOCX, ODT, RTF, HTML, TXT, MD.
- Turn a resume into proposed records: basics (profile fields), education, domains, jobs with highlights (tech, domains, numbers).
- Review by job: one Pending card per job with a tickbox per highlight; approve selected, reject, or untick lines.
- Each approved card is applied through the existing writer (whole-repo validation, diff, lock) and committed as one commit.
- Paste box: a reply from another assistant becomes memory items in Pending, checked for duplicates and contradictions against stored memory.
- A five-step Onboarding screen as designed in `Design/Ka.html`, plus a terminal command that runs the same code.
- Background job with progress: the screen never waits on one long request.

## Non-goals

- Bank statements (they have their own import flow; intake skips and says so).
- OCR for scans and images.
- Connectors (bank, email, calendar, Drive, Notion, GitHub): the Sources step shows "not available yet".
- Changing fields of a job already stored (same company and start): it is shown as "already stored" and skipped. New highlights for a stored job are allowed (see Review calls).
- Chat-history archive imports, resume generation.

## Anti-goals (a failure even if it works)

- Anything written to the data repo without an explicit approval.
- An invented number: a metric the resume does not contain.
- A silent partial import: a failed or truncated extraction must say so on the screen.
- A model failure or odd file that leaves a stuck job forever.

## Constraints

- Public code repo: no personal data in code, tests, fixtures or docs. Test documents are generated synthetic text.
- Existing rules hold: no LLM in the parser or tagging path; money is Decimal; every in-progress feature behind a flag in `config.yaml` (new flag `intake`, default off); flow docs updated with the change; tests minimal (one per risky behaviour).
- Document text is sent to the configured model provider (today OpenAI). The screen says so before upload.
- The extraction model's output is data, never instructions, and is validated by Pydantic before anything is queued.
- Writes only through `plan_change`/`apply_change`. No new write path to the YAML.

## Approaches considered

How to run extraction:

- **A. Inside the upload request.** Simplest; the screen waits 20 to 60 s with no progress and a phone connection may time out.
- **B. Background job, screen polls.** Chosen by the owner. Costs a small `intake_jobs` table and a worker thread (same pattern as chat).
- **C. Through the chat agent with an intake tool.** Non-deterministic, hits the 10-tool-call cap, does not fit cards. Rejected.

Review unit: one by one, by job, whole resume. Owner chose **by job**.

## Design (owner-decided parts marked; the rest are the designer's calls)

### Modules (`server/intake/`, flow doc `context/flows/intake.md`)

- `readers.py`: `read_document(path: Path) -> str`, dispatch on suffix. PDF via pdfplumber, DOCX via python-docx, ODT via zipfile and XML, RTF via a small RTF-to-text library, HTML via the standard library parser, TXT and MD as UTF-8. Unknown type, unreadable or empty text raises `IntakeError` with a readable message. (Call.)
- `extract.py`: `extract_resume(text, adapter, domains) -> ResumeDraft`. One model call that returns JSON matching a Pydantic `ResumeDraft` (profile fields, education, domain names, jobs with highlights). One retry when the JSON is invalid; then `IntakeError`. Text over a size cap (call: 60 000 characters) is cut and the job result says it was truncated.
- `queue.py`: turns a draft into Pending cards (below), after deterministic guards.
- `runner.py`: `run_intake(job_id, files, ...)` used by both the API thread and the CLI.
- Statement guard: a file the Scotiabank layout detector recognises is skipped with a note "use the statement import". (Call.)

### Deterministic guards on the draft (code, not the model)

- Every `number` in a highlight is kept only if its digits appear in the source text; otherwise dropped and counted in the job result.
- A highlight's `tech` and `domains` are proposals; domains are matched by name to the Domains card or stored domains, unknown ones are dropped.
- Dates are normalised to the partial-date format; a job without a start date is queued with a visible "needs a date" flag and cannot be approved until fixed. (Call.)

### Pending cards (extends the existing `pending` table)

New kind `bundle`. Payload: `title`, `section` (`basics`, `education`, `domains`, `job`), `needs` (ids of cards that must be approved first), and `items`, each `{id, label, detail, selected: true, patch}` where `patch` is a `Patch`. The Domains card gates job cards; a job card cannot be approved until Domains is approved (or the domains already exist). Existing memory items keep working unchanged.

- Approve takes `{selected: [item ids]}`. The server builds the patch list in order (job first, then its highlights with the job as parent), resolves domain names to ids, and applies the list as one change.
- One commit per card requires a batch entry point in the writer: `plan_batch(root, patches) -> ChangePlan` that applies patches in sequence to the temp copy, validates the whole repo once, and returns one diff. `apply_change` then commits once. (Required; the builder verifies the writer allows this without weakening its checks.)
- Re-running intake on the same file skips jobs already stored and highlights already present in a job (normalised text match). Basics: shows old and new values; only changed fields appear.

### Memory paste

`POST /api/intake/memory {text, source}` runs the existing extraction instruction (new facts, `replaces` for contradictions) on the pasted text and queues memory items through `queue_memory` with `source="import:<assistant>"`. Imported memory is shown as unverified in the card text. The model input is capped like documents.

### Jobs and API (`server/api/intake.py`, flag `intake`)

- Table `intake_jobs(id, status [queued|running|done|failed], step, message, result_json, created_at)`.
- `POST /api/intake/documents` (multipart, up to 5 files, 10 MB each) stores files under `<data_repo>/local/intake/<job>/`, starts a worker thread, returns `{job_id}`. `GET /api/intake/{job_id}` returns status, a human `step` ("Reading resume", "Found 4 jobs"), counts, warnings (truncated, dropped numbers, skipped files), and the pending card count.
- `POST /api/intake/basics {name, city, region, country, role}` queues a Basics card from the form (Step 1).
- A job interrupted by a restart is marked `failed: interrupted` at startup. Only one document job runs at a time (409 otherwise).
- CLI: `ka intake FILE... [--memory FILE --source NAME]` runs `run_intake` in the foreground and prints the card count; `ka pending` lists bundle cards; `approve ID` applies all items.

### Screen (`ui/src/features/onboarding/*`, route `/onboarding`)

The five steps in `Design/extracted/app.html`: Basics, Documents (drop zone, file list, "Ka sends these to <provider>"), Sources (three rows, Connect disabled with "not available yet"), Memory paste (assistant picker, prompt to copy, paste box), Review ("Everything Ka found is waiting in Pending"). Progress from polling `GET /api/intake/{id}` every second. Entry: a "Go through setup again" row in Settings and a one-line banner in chat while the profile has no jobs. The Pending screen gains the by-job card: title, list of lines with tickboxes and their tags, Approve selected, Reject, a "needs Domains first" state, and an "already stored" state. Phone layout follows the design's phone page.

### Tests (minimal)

- One reader test per format using generated synthetic files (a parametrised test).
- Extraction: invalid JSON retried once then fails readably; a number absent from the source is dropped.
- Approve: a job card applies as exactly one commit with correct highlight ids; approving a job before Domains is refused; unticked lines are not written; re-running skips stored jobs.
- Runner: a failing model leaves the job `failed` with a message; an interrupted job is failed at startup.
- API: upload rejects oversize and unsupported types; second concurrent job is 409.
- UI: a reducer or helper test for the card's tick state; the rest checked in the browser against the design.

## Review calls (settled after an independent read of this design; marked as the designer's calls)

- **Basics role.** `Profile` has no `role` field. The Basics form's "what do you do" is written to `profile.summary` as one line when the summary is empty; otherwise it is queued as a memory fact. No schema change.
- **Domains gate.** A job card needs the Domains card to be *decided*, not approved. If Domains is rejected, or a domain is unticked, highlight tags that use it are dropped and the job can still be approved.
- **Missing `employment_type`.** Defaults to `full_time`; the card labels it "full time (assumed)".
- **Re-run on a stored job.** The job itself is skipped, but highlights whose normalised text is not already in that job become a card "Add N highlights to <job>".
- **Memory paste is a job too.** Same `intake_jobs` table (a `kind` column: `documents` or `memory`), same one-at-a-time 409 rule, same polling.
- **Uploaded files.** Deleted when the job ends (done or failed). Nothing is kept; a re-run needs the file again.
- **Agent access.** The chat agent neither sees nor approves `bundle` cards; approval is an owner action in the UI or CLI.

## Owner's answers to the reviewer's open questions

- **Profile fields a resume may propose:** name, emails, phones, location, links, languages. Date of birth and home addresses are never proposed; the owner enters them by hand. The extraction schema simply has no fields for them.
- **Flagged jobs (for example no start date):** no editing on the card in v1. The card shows the reason and cannot be approved; the owner rejects it and states the fix in chat, which goes through the normal approved change.

## Left to the builder

Model prompt wording and the JSON schema; the RTF library choice; exact file-size and text caps beyond those named; the card's detail copy; whether `needs` is stored as ids or a section name; progress step wording.

## Risks

- The writer batch entry point is the one structural change; if it cannot keep whole-repo validation, fall back to one commit per item and tell the owner.
- A resume with unusual layout can yield a poor extraction. The review-by-job step is the safety net, not model accuracy.
- Document text goes to the model provider; the owner has accepted this for chat data and the screen states it again.
