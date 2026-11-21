/** Session recovery: when the session ends mid-use, remember where the owner was and what they
 * had typed, send them to login, and put both back afterwards. sessionStorage only: it dies with
 * the tab and never leaves this device. */

const RETURN = 'ka:return'
const DRAFT = 'ka:draft'

let draftSource: (() => string) | null = null

/** The chat composer registers a getter so an expired session can keep its unsent text. */
export function registerDraft(get: (() => string) | null) {
  draftSource = get
}

function store(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    /* storage blocked: recovery is best effort */
  }
}

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

export function saveReturn(path: string, draft: string) {
  store(RETURN, JSON.stringify({ path, draft }))
}

/** Read the return target once; its draft moves to the composer's slot. */
export function takeReturn(): { path: string; draft: string } | null {
  const raw = read(RETURN)
  store(RETURN, null)
  if (!raw) return null
  try {
    const r = JSON.parse(raw) as { path: string; draft: string }
    if (r.draft) store(DRAFT, r.draft)
    return r
  } catch {
    return null
  }
}

export function takeDraft(): string {
  const d = read(DRAFT) ?? ''
  store(DRAFT, null)
  return d
}

/** `sent` is a message on its way out: the composer already cleared it, so keep it here. */
export function capture(path: string, sent = '') {
  const safe = path.startsWith('/login') ? '/chat' : path
  saveReturn(safe, draftSource?.() || sent)
}

/** Called by the API client on any 401: keep the place, then show the login screen. */
export function onUnauthorized(sent = '') {
  if (window.location.pathname.startsWith('/login')) return
  capture(window.location.pathname, sent)
  window.location.assign('/login')
}
