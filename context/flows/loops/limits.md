# Loops: limits, switches and failure cases

Part of the [loops flow](index.md).

| Item | Default / where |
|---|---|
| Run limits (`RunLimits`) | 300 s, 20 model calls, 30 tool calls, $0.50 per run; a hit stops the run with an alert |
| Cost when the provider reports none | estimated from tokens with `prices` in `config.yaml` (an unlisted model at the dearest price); no prices, no estimate |
| Active loops per account | 10 agent loops (built-ins do not count); the 11th gets 409 "You have 10 active loops. Pause one first." |
| Runs at once per account | one (`service.execute` holds a per-account lock); a scheduled run that finds one going waits for it (up to 6 minutes, longer than one run's limit), so two loops due at the same minute both run; Run now gets 409 "This loop is already running.", or "Another loop is running. Try again when it finishes." when it is a different loop |
| Workers | loop jobs run on the scheduler's `loops` pool (4 threads), apart from imports, extraction and the watchdog (`default`, 10) |
| Run now | `POST /api/loops/{id}/run` starts the run on its own thread and returns 202 `{"started": true}`; the screen shows "Running…" and polls `/runs` every 2 s until a newer run has ended (at most 5 minutes) |
| Stop switch | Settings or `ka loops pause` (`app_state loops_paused`); flag `loops` off stops everything |
| Watchdog | every 15 min: a task with no check-in for twice its interval (daily: 26 h) or a card older than 3 days raises one alert per missed check-in: the key includes the last check-in, so a dismissed alert does not silence a later miss |
| Shadow to direct | manual, per task; the loops screen shows approved and rejected card counts |

## Failure cases

| Case | Result |
|---|---|
| Body raises | run `failed` with the exception type only; alert card |
| Limit hit | run `stopped`, reason names the limit; alert card |
| Stop switch on / task paused / flag off | run `skipped` with the reason |
| Bad trigger | refused at creation by APScheduler's own trigger check (`interval` at least 15 minutes); a bad stored one is skipped, never stops the scheduler |
