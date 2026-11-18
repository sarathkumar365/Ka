# Flow: settings

**Summary.** `GET /api/settings` returns the configured models and the private model chain (provider and model name only) and feature flags from `config.yaml`. The screen follows the design's rows: Models (each role and the money model in a select), Connected accounts, Features (each flag with a plain label and a switch), Appearance, and More (Activity log, Go through setup again). Only the theme can change here (stored in the browser); model selects and flag switches show the state and say "Set in config.yaml". With flag `google` on, Connected accounts has a Google row (Connect, Disconnect, or Reconnect only when the error says `reconnect Google`), a Drive statements row with Sync now and skipped files, and a Sheet copy row with Copy now (see [google.md](google.md)).

## Why this way

- **Read-only.** A UI write to `config.yaml` can break startup. Editing stays in the file.
- **Allow-list response.** Only provider, model and flags are returned, never keys or paths.

## Failure cases

| Case | Result |
|---|---|
| `localStorage` blocked | theme works until reload |

Source: `server/api/settings.py`, `ui/src/features/settings/*`, `ui/src/lib/theme.ts`

Interview questions: [settings.interview.md](interview/settings.interview.md)
