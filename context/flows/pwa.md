# Flow: PWA and phone access

**Summary.** The UI is an installable web app: manifest, icons, iOS meta tags, safe-area padding and a service worker that caches the app shell only. `/api` is never cached. The server listens on `127.0.0.1` only; a phone reaches it through `tailscale serve`. The start URL `/chat` sends a signed-out person to the home screen (`/welcome`), then sign-up or sign-in.

## New machine

`scripts/setup.sh` sets up a fresh macOS or Linux box from a clone. Each step checks first and skips what exists: git and curl, uv with Python 3.13, Node 22+, `uv sync`, the UI build, an empty committed data repo at `~/ka-data` (or `KA_DATA`), `config.yaml`, an `.env` with empty key names, then `ka check`. It never overwrites `config.yaml`, `.env` or a data repo. The data repo gets a repo-local git identity because the writer commits every approval and a fresh box often has none. If Tailscale is logged in, the script adds the machine's tailnet name to `ui_hosts` and runs `tailscale serve`, but only when the tailnet has HTTPS on; without it `tailscale serve` waits for a browser prompt. `KA_SKIP_TAILSCALE=1` skips that step. The script does not install a service, so Ka stops if the machine reboots or its terminal closes.

## Steps for an iPhone

1. `ka serve` (flag `web_ui` on).
2. `tailscale serve --bg 8000` gives an HTTPS tailnet URL.
3. Add that hostname to `ui_hosts` in `config.yaml`; restart `ka serve`.
4. Open the URL in Safari, Share, Add to Home Screen.

## Phone layout

The app fills the dynamic viewport (`100dvh`), so Safari's toolbar never hides the composer, and nothing has a minimum height, so a sideways phone fits without the whole page scrolling. Page bottoms add the home-bar inset (`--safe-b`). iOS does not shrink the layout when the keyboard opens; it slides the page and can leave it slid. `watchKeyboard` (`ui/src/lib/viewport.ts`) reads `visualViewport` and publishes the keyboard height as `--kb`, so the chat composer sits right on the keyboard, and scrolls the page back to 0 once the keyboard closes. Inputs and selects drop Safari's own styling (`appearance: none`; selects draw their own chevron), inputs stay 16 px so iOS does not zoom, and the page itself does not bounce (`overscroll-behavior`). Scrollbars are hidden on touch screens.

## Why this way

- **Tailnet plus accounts, no public bind.** The tailnet limits who can reach Ka; accounts and sessions limit what each person sees (sign-up is open to anyone on the tailnet, see [login.md](login.md)). The `Host` allow-list blocks DNS-rebinding from web pages, and writes must come from Ka's own origin.
- **Shell-only cache.** Offline shows the app; data calls fail visibly instead of showing stale money figures.

## Not verified here

The service worker could not register in the desktop app's embedded browser, and the iPhone steps were not run. On first try check: the home-screen icon, standalone launch, the status bar, and that an offline reload shows the shell with an error on data calls.

## Failure cases

| Case | Result |
|---|---|
| Host not in `ui_hosts` | 400 |
| Service worker unsupported or blocked | app works without offline shell |
| POST from another site's page (Origin not allowed) | 403 "cross-site request refused" |

Source: `ui/vite.config.ts`, `ui/index.html`, `ui/src/lib/viewport.ts`, `ui/src/styles.css`, `ui/scripts/make-icons.mjs`, `server/api/app.py`, `scripts/setup.sh`

Interview questions: [pwa.interview.md](interview/pwa.interview.md)

**Updates.** The service worker is registered in `ui/src/main.tsx` with `registerSW({ immediate: true })` (`injectRegister: false`). In `autoUpdate` mode the page reloads once a new version takes over, so an old cached screen never lingers after a server update. Unsent onboarding input is guarded by its leave prompt. Not checked in the in-app browser, which does not register service workers.
