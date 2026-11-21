# Post-build setup (owner)

Everything below needs your keys, accounts or judgment. Nothing here is required for the code to run; each item turns on one piece.

1. **Review and commit.** All next-phase work is uncommitted on branch `next-phase`. Read the diff (`git diff main`), then commit; suggested messages are in `Docs/superpowers/plans/2026-11-20-ka-next-phase.md` at the end of each task.
2. **Keys in `.env`.** Names are in `.env.example`. Set now: `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `EXA_API_KEY`, `BRAVE_SEARCH_API_KEY`, `FIRECRAWL_API_KEY`. Still missing: `TMDB_API_TOKEN` (TMDB read access token), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`.
3. **Models in `config.yaml`.** Check the Haiku slug at https://openrouter.ai/api/v1/models (the live list showed `anthropic/claude-haiku-5.5[1m]`), then set:
   - `models.default`: OpenRouter Haiku, `zdr: true`, `cache: true`, optional `fallbacks`.
   - `models.small`: a cheap model for nightly extraction and page summaries.
   - `models.grader`: Opus, for the eval judge.
   - Optional: `reasoning: medium` on the `private_models` entry for harder money questions.
4. **First start (multi-account).** Nothing moves across from the old layout. Stop `ka serve`, delete `~/Projects/ka-data/local/ka.db` and any root-level personal YAML in `~/Projects/ka-data` (commit that in the data repo), remove `google.drive_folder_id`/`sheet_id` from `config.yaml` (they are ignored now), then `uv run ka serve`, open the app, and use **Create account** on the home screen. Each person who signs up does the same. `uv run ka users list` shows the accounts; `uv run ka users reset-password NAME` sets a new password.
4b. **Google for other people.** In Google Cloud > OAuth consent screen, add each person as a test user (or publish the app). A Desktop OAuth client only accepts loopback callbacks, so for sign-in from a phone create a Web OAuth client, point `google.client_file` at it, and add the tailnet address callback as an authorised redirect URI: `https://<your-machine>.<tailnet>.ts.net/api/google/callback` (and `http://localhost:8000/api/google/callback` for local use). Each person then connects Google and enters their own Drive folder id and Sheet id in Settings.
5. **Langfuse.** `git clone https://github.com/langfuse/langfuse.git`, edit every `# CHANGEME` secret, `docker compose up -d`, open http://localhost:3000, create a project and its keys, put them in `.env`, set `tracing: true`, restart `ka serve`. Check one chat appears as a trace.
6. **Web search.** Set `web_search: true`. Ask "is <a recent film> on Netflix in Canada?" and "how much did I spend in November?" (the second must not search).
7. **Movies.** Read TMDB's terms of use (they restrict using TMDB data with AI applications). Only then add `TMDB_API_TOKEN` and set `movies: true`.
8. **Loops.** Set `loops: true`. The built-in statement import runs in shadow mode: new Drive statements arrive as cards in Pending. Switch it to direct on the Loops screen once you trust it. Try "check my spending every Monday at 8" in chat: it asks before saving the task.
9. **Evals.** Write the first eval set (parked), including the September-question case. Run `KA_LIVE_EVALS=1 uv run pytest tests/evals/test_live.py -m regression`, then `uv run python -m tests.evals.compare` after each prompt, model or tool change.
