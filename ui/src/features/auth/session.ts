/** Session recovery: when the session ends mid-use, remember where the person was and what they
 * had typed, send them to login, and put both back afterwards, only for that same account.
 * sessionStorage only: it dies with the tab and never leaves this device. */

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

let currentUser: string | null = null

/** Set from every auth status read, so a saved place and draft know whose they are. */
export function rememberUser(username: string | null) {
  currentUser = username
}

type Saved = { path: string; draft: string; username: string | null }

export function saveReturn(path: string, draft: string, username: string | null) {
  store(RETURN, JSON.stringify({ path, draft, username }))
}

/** Read the return target once, only for the account that left it; its draft moves to the
 * composer's slot. Another account signing in on this device gets nothing. */
export function takeReturn(username: string): { path: string; draft: string } | null {
  const raw = read(RETURN)
  store(RETURN, null)
  if (!raw) return null
  try {
    const r = JSON.parse(raw) as Saved
    if (!r.username || r.username !== username) return null
    if (r.draft) store(DRAFT, JSON.stringify({ draft: r.draft, username }))
    return { path: r.path, draft: r.draft }
  } catch {
    return null
  }
}

export function takeDraft(): string {
  const raw = read(DRAFT)
  store(DRAFT, null)
  if (!raw) return ''
  try {
    const d = JSON.parse(raw) as { draft: string; username: string }
    return currentUser && d.username === currentUser ? d.draft : ''
  } catch {
    return ''
  }
}

/** `sent` is a message on its way out: the composer already cleared it, so keep it here. */
export function capture(path: string, sent = '') {
  const safe = /^\/(login|signup|welcome)/.test(path) ? '/chat' : path
  saveReturn(safe, draftSource?.() || sent, currentUser)
}

/** Called by the API client on any 401: keep the place, then show the login screen. */
export function onUnauthorized(sent = '') {
  if (/^\/(login|signup|welcome)/.test(window.location.pathname)) return
  capture(window.location.pathname, sent)
  window.location.assign('/login')
}
