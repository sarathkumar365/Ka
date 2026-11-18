# Ka Onboarding "Send Once" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboarding collects basics, documents and memory exports without sending anything, then a final "Send to Ka" screen sends everything in one request, shows a breathing Ka mark while one background job reads it all, and ends on a summary with "Review in Pending".

**Architecture:**
- The onboarding page holds every step's input in one React state object; the steps become controlled forms with no requests of their own.
- A new multipart endpoint `POST /api/intake/onboarding` takes the files, the basics and the memory items together and starts one `onboarding` intake job.
- `runner.run_onboarding_job` reuses the existing pieces: `queue_basics`, the documents extraction loop and `run_memory`'s per-source loop.
- The job result carries counts for the summary.
- The service worker reloads the page when a new version takes over, so an old cached UI never lingers.

**Tech Stack:** FastAPI (multipart), existing intake runner, React state, one 2D canvas render loop for the ring, vite-plugin-pwa `virtual:pwa-register`, vitest, pytest.

**Spec:**
- The owner's request (2026-11-17): capture everything as you go; one final screen sends it to the agent; a breathing Ka animation while it works; everything in one go, not step by step.
- The owner's follow-up: every transition must be smooth, from Send through reading to Pending, built with the owner's `living-transitions` skill (the first GSAP-and-particles build was rejected and replaced).
- The owner's answers:
  - lose everything on reload, but warn first;
  - keep the default model;
  - after sending, show a summary, then Pending.
- The base design is `Docs/superpowers/specs/2026-11-17-onboarding-intake-design.md`. Its guards, caps, by-job cards and approval rules all stay.

## Global Constraints

- Nothing leaves the browser before the owner presses **Send to Ka** on the last step. Next and Back only change the step.
- Steps are Basics, Documents, Sources, Memory, Send. The Send step shows what will be sent (name, file names, assistants), the disclosure line "Ka sends this to <provider>", and the Send to Ka button.
- Leaving with unsent input shows a warning:
  - a `beforeunload` prompt on reload or close;
  - a `confirm()` on Skip for now.
  - Nothing is saved in the browser.
- Limits stay as today: up to 5 files of 10 MB each, suffixes from `SUPPORTED`, up to 5 memory items of 60 000 characters each, and basics fields as in `BasicsBody`.
- One intake job at a time (409 otherwise), and a job interrupted by a restart is failed at startup. Both stay as today.
- The model is `models.default` (owner's call). Uploaded files are deleted when the job ends.
- Motion (redesign, 2026-11-17, after the owner rejected the first version; follows the owner's `living-transitions` skill). One object morphs, nothing swaps:
  1. Send: the ring takes the Send button's exact rect, then rounds into a 112 px ring at the stage centre while the form fades (220 ms).
  2. Thinking: the ring splits into one arc per part in `result.parts` (basics, each file, each assistant); arc brightness follows that part's real state; the whole ring breathes on a 3.2 s cycle.
  3. Done (at least 900 ms after Send): arcs join into one ring; `result.cards` counts up inside it; the summary fades in below.
  4. Review in Pending: the ring shrinks onto the Pending bell's badge, labelled with that badge's count, and hands over to the real badge while Pending fades in and its cards rise 60 ms apart. With nothing waiting, it fades in place.
  5. Failure: the ring morphs back into the button.
  - One canvas loop in `features/onboarding/KaRing.tsx`, mounted in the Shell; phases only update a ref; easing is time-based (`ring.settleFactor`). Reduced motion snaps every change. No GSAP, no particles.
- Summary copy: `Ka found {jobs} job(s), {highlights} highlight(s) and {memories} memory item(s).` Warnings are listed under it, then one button: **Review in Pending**. That button marks onboarding done and opens `/pending`.
- A failed job shows its message and a **Try again** button, which resends the same input still held in the page.
- Public repo: synthetic test data only. Tests minimal: one per risky behaviour.
- Commits: commit guard; touch `.claude/.reviewed` only after a yes; no Claude trailers; noreply author.

## Review Focus

1. Send with only some inputs, for example memory only, no files and no basics. The job runs only what was given and succeeds (T1 test).
2. A memory source fails but the resume works. The job is done, with a warning, and the cards are queued (T1 test).
3. The request has more than 5 files or an oversize body. It gets a 413 or 400 before anything is spooled (T2 test, extending the upload-size middleware path list).
4. The owner presses Send twice quickly. The second request gets a 409 and the UI keeps showing the first job (T2 test plus the UI disabling the button while sending).
5. Reload in the middle of the steps. The browser shows a leave warning, and after the reload the page starts empty (T3 browser check).
6. The job finishes before the Send transition ends, or the owner leaves Pending mid-dissolve. The choreography completes or is cleaned up, with no stuck canvas or orphan loop (T4 browser check plus tween kill on unmount).

---

### Task 1: One job for everything

**Files:**
- Modify: `server/intake/runner.py`, `server/store/db.py` (job kind gains `onboarding`)
- Test: `tests/intake/test_runner.py`

**Interfaces:**
- Consumes: `queue_basics(db, data, name, city, region, country, role, now) -> int`, `read_document`, `is_statement`, `extract_resume`, `queue_draft(...) -> QueueResult`, and `import_memory(text, source, db, data, adapter, now, seen) -> int`.
- Produces:
  - `Basics(name: str, city: str, region: str, country: str, role: str)`, a dataclass in `runner.py`.
  - `run_onboarding_job(job_id: str, paths: list[Path], basics: Basics | None, memory: list[tuple[str, str]], cfg: Config, adapter: Adapter, now=datetime.now) -> None`. The job result is `{"cards": int, "jobs": int, "highlights": int, "memories": int, "skipped": list[str], "warnings": list[str]}`.
  - Order: basics first, then documents (all extracted before any is queued, as today), then memory sources in turn.
  - A document extraction failure becomes a warning, not a job failure, unless nothing at all was produced. In that case the job is `failed` with the joined warnings.
  - `jobs` and `highlights` are counted from the queued `job` cards and their items. `memories` is the sum of `import_memory` returns.
  - Refactor `run_documents_job` and `run_memory_job` to call the same inner helpers `_documents(...)` and `_memory(...)`, so the CLI keeps working unchanged.
- [ ] **Step 1: Write the failing tests:**
  - `test_onboarding_job_runs_only_what_was_given`: memory only, one source. The job is done, `memories == 1`, and `jobs == 0`.
  - `test_onboarding_job_all_parts`: basics plus one resume file (the existing synthetic `GOOD` draft), plus two memory sources where the second raises `AdapterError`. The job is done. `jobs >= 1`, `memories == 1`, one warning names the failed source, and a basics card exists.
  - `test_onboarding_job_nothing_usable_fails`: one unreadable file and a failing memory source. Status is `failed`.
- [ ] **Step 2: Run** `uv run pytest tests/intake/test_runner.py -q`. Expected: FAIL (name missing).
- [ ] **Step 3: Implement** the code.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: one intake job for basics, documents and memory`.

### Task 2: Endpoint for the single send

**Files:**
- Modify: `server/api/intake.py`, `server/api/app.py` (the `cap_upload_size` middleware also covers `/api/intake/onboarding`; its limit becomes `UPLOAD_LIMIT + 5 * 60_000 + 64 KiB`)
- Test: `tests/api/test_intake.py`

**Interfaces:**
- Produces: `POST /api/intake/onboarding`, multipart, returning `{job_id}`. Form fields:
  - `files` (0 to 5 `UploadFile`);
  - `basics` (optional JSON string matching `BasicsBody`);
  - `memory` (optional JSON string: a list of `{source, text}` matching `MemoryItem`, at most 5).
- At least one of the three must be non-empty, otherwise 400 `nothing to send`. File checks (count, size, suffix) are the same as `/intake/documents`. A bad JSON field gives 422.
- Files are saved under `<data_repo>/local/intake/<job>/` exactly as `/intake/documents` does, then a thread runs `run_onboarding_job`.
- `/intake/documents`, `/intake/memory` and `/intake/basics` stay for the CLI and API, but the UI no longer calls them.
- [ ] **Step 1: Write the failing tests:**
  - `test_onboarding_send_starts_one_job`: one synthetic `.txt` file, basics, and one memory item. The response is 200 with a `job_id`, and the job kind is `onboarding`.
  - `test_onboarding_send_needs_something`: an empty form gives 400.
  - `test_onboarding_send_while_running_is_409`.
  - `test_onboarding_send_oversize_refused_early`: a Content-Length over the new limit gives 413.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_intake.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the code.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: single onboarding send endpoint`.

### Task 3: Collect-then-send screens, breathing mark, summary

**Files:**
- Create: `ui/src/features/onboarding/draft.ts`, `ui/src/features/onboarding/draft.test.ts`, `ui/src/features/onboarding/StepSend.tsx`
- Modify: `ui/src/features/onboarding/{OnboardingPage,StepBasics,StepDocuments,StepMemory}.tsx`, `ui/src/lib/api.ts`, `ui/src/styles.css`
- Delete: `ui/src/features/onboarding/StepReview.tsx` (replaced by `StepSend`)

**Interfaces:**
- Consumes: T2's endpoint, `useIntakeJob(jobId)`, and `memory.ts` (`toItems`, `MemoryEntry`).
- Produces:
  - `draft.ts`:
    - `type Draft = { basics: { name: string; where: string; role: string }; files: File[]; memory: MemoryEntry[] }`
    - `emptyDraft(): Draft`
    - `hasInput(d: Draft): boolean` (any basics field trimmed, any file, or any memory text)
    - `toForm(d: Draft): FormData` (basics as JSON only when filled; `where` split into city, region and country as StepBasics does today; memory via `toItems`, only when non-empty)
    - `summaryLine(r: {jobs: number; highlights: number; memories: number}): string`, which produces the exact copy in Global Constraints.
  - `api.sendOnboarding(form: FormData): Promise<{ job_id: string }>`.
  - The steps take `value` and `onChange` props, with no `useMutation` inside. StepDocuments keeps its drop zone and file list but has no upload button.
  - `StepSend` shows what will be sent and the disclosure, with Send to Ka disabled when `!hasInput`.
    - While sending or while the job runs, it renders the mark and the job `step` text centred. Task 4 adds the motion.
    - On done, the summary line, the warnings and Review in Pending.
    - On failure, the message and Try again.
  - `OnboardingPage` holds `draft` state.
    - While `hasInput(draft)` is true and the job has not started, a `beforeunload` handler is active.
    - Skip for now asks `confirm('Leave setup? What you entered is not saved.')` when there is input.
    - The Next button is hidden on the Send step.
- [ ] **Step 1: Write the failing vitest tests** in `draft.test.ts`:
  - `hasInput` is false for `emptyDraft()` and for whitespace-only fields, and true for one file or one memory text.
  - `toForm` omits `basics` when empty and includes `memory` as a JSON list in lower case.
  - `summaryLine({jobs: 2, highlights: 7, memories: 4})` equals `'Ka found 2 job(s), 7 highlight(s) and 4 memory item(s).'`
- [ ] **Step 2: Run** `cd ui && npx vitest run src/features/onboarding`. Expected: FAIL.
- [ ] **Step 3: Implement** the code with no animation yet: a static mark, and an instant switch between states.
- [ ] **Step 4: Run** `npx vitest run`, `npx tsc -b` and `npm run build`. Then check in the browser against a scratch data repo (`KA_CONFIG`, intake flag on):
  - fill basics and one memory paste, and pick a synthetic `.txt` resume;
  - confirm no network request goes to `/api/intake/*` before Send (read network requests);
  - Send, see the mark with step text, then the summary and Review in Pending, which opens `/pending` with the cards;
  - reload mid-steps and see the leave warning;
  - check at phone width.
  - Expected: all true.
- [ ] **Step 5: Commit** `feat: onboarding collects everything and sends once`.

### Task 4: The ring (redesigned)

Superseded the first motion build (GSAP fly-in, particle dissolve), which the owner rejected. Built instead, per Global Constraints "Motion": server `result.parts` per part (`test_onboarding_job_reports_each_part`, `test_onboarding_parts_without_basics`); `features/onboarding/ring.ts` (`approach`, `settleFactor`, `arcs`, `partAlpha`, tested in `ring.test.ts`); `features/onboarding/KaRing.tsx` (layer and loop); `StepSend.tsx` drives it; Pending cards rise on arrival (CSS). Verified frame by frame in headless Chrome: every phase, mid-morph frames, phone width, reduced motion, the error state and a second pass.

### Task 5: New version replaces the cached UI, docs

**Files:**
- Modify: `ui/src/main.tsx`, `ui/vite.config.ts` (`injectRegister: false`), `context/flows/intake.md`, `context/flows/pwa.md`, `context/decisions.md`

**Interfaces:**
- Produces: in `main.tsx`, `registerSW({ immediate: true })` from `virtual:pwa-register`. In `autoUpdate` mode it reloads the page once the new service worker takes control, so the owner never sees an old cached screen after a server update.
- [ ] **Step 1: Implement** the code. Then build twice with a visible text change between builds, and in the browser confirm the second build appears after a single reload, without closing the tab. Expected: the new text shows after one reload.
- [ ] **Step 2: Docs.** Use the `flow-docs` skill:
  - `intake.md`: replace the step-by-step sending with "collect, then Send once", and add the onboarding job, the endpoint, the summary and the leave warning.
  - `pwa.md`: auto-reload on update.
  - `decisions.md`: addendum with the owner's three answers.
- [ ] **Step 3: Run** `uv run pytest -q`, `uv run ruff check .`, `cd ui && npx vitest run && npx tsc -b && npm run build`, and `uv run python scripts/commit_guard.py`. Expected: all pass, and the guard exits 0.
- [ ] **Step 4: Commit** `feat: reload on new version; docs for send-once onboarding`.
