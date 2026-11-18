# Flow: PWA and phone access

**Summary.** The UI is an installable web app: manifest, icons, iOS meta tags, safe-area padding and a service worker that caches the app shell only. `/api` is never cached. The server listens on `127.0.0.1` only; a phone reaches it through `tailscale serve`.

## Steps for an iPhone

1. `ka serve` (flag `web_ui` on).
2. `tailscale serve --bg 8000` gives an HTTPS tailnet URL.
3. Add that hostname to `ui_hosts` in `config.yaml`; restart `ka serve`.
4. Open the URL in Safari, Share, Add to Home Screen.

## Why this way

- **No auth, no public bind.** The tailnet is the access control. The `Host` allow-list blocks DNS-rebinding from web pages.
- **Shell-only cache.** Offline shows the app; data calls fail visibly instead of showing stale money figures.

## Not verified here

The service worker could not register in the desktop app's embedded browser, and the iPhone steps were not run. On first try check: the home-screen icon, standalone launch, the status bar, and that an offline reload shows the shell with an error on data calls.

## Failure cases

| Case | Result |
|---|---|
| Host not in `ui_hosts` | 400 |
| Service worker unsupported or blocked | app works without offline shell |
| POST from another site's page (Origin not allowed) | 403 "cross-site request refused" |

Source: `ui/vite.config.ts`, `ui/index.html`, `ui/scripts/make-icons.mjs`, `server/api/app.py`

Interview questions: [pwa.interview.md](interview/pwa.interview.md)

**Updates.** The service worker is registered in `ui/src/main.tsx` with `registerSW({ immediate: true })` (`injectRegister: false`). In `autoUpdate` mode the page reloads once a new version takes over, so an old cached screen never lingers after a server update. Unsent onboarding input is guarded by its leave prompt. Not checked in the in-app browser, which does not register service workers.
