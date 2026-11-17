# Flow: settings

**Summary.** `GET /api/settings` returns the configured models and the private model chain (provider and model name only) and feature flags from `config.yaml`. The screen is read-only; the theme toggle is stored in the browser.

## Why this way

- **Read-only.** A UI write to `config.yaml` can break startup. Editing stays in the file.
- **Allow-list response.** Only provider, model and flags are returned, never keys or paths.

## Failure cases

| Case | Result |
|---|---|
| `localStorage` blocked | theme works until reload |

Source: `server/api/settings.py`, `ui/src/features/settings/*`, `ui/src/lib/theme.ts`

Interview questions: [settings.interview.md](settings.interview.md)
