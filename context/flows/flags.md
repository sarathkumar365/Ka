# Flow: feature flags

**Summary.** Every in-progress feature sits behind a flag in `config.yaml`, default off. `server/flags.py` holds the one list of known flags (`FLAGS`) and the one check (`is_on`); config loading rejects any flag name not in that list, so a typo stops startup instead of silently leaving a feature off. Auth and toolkits are part of the system and have no flag.

```mermaid
flowchart LR
    Y[config.yaml flags] -->|Config validator: names in FLAGS| C[Config]
    C --> I[is_on cfg, name]
    I --> T[tool and toolkit visibility]
    I --> R[require_flag: API routes 404]
    I --> J[scheduler jobs in app._jobs]
    I --> X[tracing setup]
    I --> S[/api/settings flag_info]
```

## Worked example

`web_search: true` in `config.yaml`. `load_config` builds `Config`; `_known_flags` checks every name against `FLAGS`. When the loop lists tools, `visible_tools` keeps `web_search` and `fetch_page` because their `Tool.flag` is on. Turn it off and they leave the specs on the next model call, even in an open chat. Routes guarded with `Depends(require_flag("loops"))` answer 404 while `loops` is off. `/api/settings` returns `flag_info` (name, description, on) so Settings can show them; flags are changed in the file, not in the UI.

## Gate points

| Gate | Where |
|---|---|
| Tool visible to the model | `Tool.flag`, `Manifest.flag` via `visible_tools` / `available` |
| API route exists | `require_flag(name)` dependency |
| Background job scheduled | `server/api/app.py` `_jobs` |
| Tracing exporter | `server/tracing.py` `setup_tracing` |
| CLI command allowed | `server/cli.py` |

## Why this way

- **One list, checked at load.** A misspelt flag is an error, not a silent "off".
- **No flag library.** Booleans in YAML plus a dict in code are enough for one owner.
- **Remove the flag when the feature is stable**, deleting its entry in `FLAGS` and every `is_on` for it.

## Failure cases

| Case | Result |
|---|---|
| Unknown name in `config.yaml` | `ConfigError: ... unknown flags: <name>` at startup |
| `is_on(cfg, "typo")` in code | `KeyError`, caught by tests |
| Flag missing from config | off |

Source: `server/flags.py`, `server/config.py`, `server/api/settings.py`
