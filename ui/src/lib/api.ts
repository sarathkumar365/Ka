import { onUnauthorized, rememberUser } from '../features/auth/session'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

/** FastAPI sends `detail` as text, or for a failed body check as a list of `{msg}` items. */
export function detailText(body: unknown, fallback: string): string {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length) {
    const msg = (d[0] as { msg?: unknown }).msg
    if (typeof msg === 'string') return msg.replace(/^Value error, /, '')
  }
  return fallback
}

async function readDetail(res: Response): Promise<string> {
  try {
    return detailText(await res.json(), res.statusText)
  } catch {
    return res.statusText
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { 'content-type': 'application/json' } : undefined,
  })
  if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized()
  if (!res.ok) {
    throw new ApiError(res.status, await readDetail(res))
  }
  return res.json() as Promise<T>
}

export type ConversationRow = { id: string; title: string; started_at: string; last_at: string }
type HistoryItem =
  | { kind: 'user' | 'assistant'; text: string }
  | { kind: 'tool'; name: string; args: Record<string, unknown>; result: string | null }
export type MemoryRow = {
  kind: 'memory'
  id: number
  type: 'fact' | 'preference' | 'rule'
  text: string
  old: string | null
  source: string | null
  created_at: string
}
type BundleItem = { id: string; label: string; detail: string; selected: boolean }
export type BundleRow = {
  kind: 'bundle'
  id: number
  title: string
  section: 'basics' | 'education' | 'domains' | 'job' | 'highlights' | 'categories' | 'types'
  blocked: string | null
  note: string | null
  needs: number[]
  ready: boolean
  items: BundleItem[]
  source: string | null
  created_at: string
}
export type StatementRow = {
  kind: 'statement'
  id: number
  file: string
  statement_id: string
  account: string
  period_start: string
  period_end: string
  rows: number
  money_in: string // Decimal as text: never parsed to a number
  money_out: string
  checks: string[]
  unknown_merchants: number
  already_imported: boolean
  source: string | null
  created_at: string
}
export type ToolWriteRow = {
  kind: 'tool_write'
  id: number
  tool: string
  summary: string
  diff: string
  run_id: number | null
  after_untrusted: boolean
  source: string | null
  created_at: string
}
export type AlertRow = {
  kind: 'alert'
  id: number
  title: string
  detail: string
  source: string | null
  created_at: string
}
export type PendingRow = MemoryRow | BundleRow | StatementRow | ToolWriteRow | AlertRow
export type AuthStatus = { user: string | null; username: string | null; min_password: number; username_rule: string }
export type TaskRun = {
  id: number
  task_id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'ok' | 'stopped' | 'failed' | 'skipped'
  reason: string
  model_calls: number
  tool_calls: number
  cost_usd: string
  result: Record<string, unknown>
}
export type Trigger =
  | { type: 'interval' | 'folder'; minutes: number; source?: string }
  | { type: 'cron'; hour: number; minute: number; day_of_week?: string }
export type LoopTask = {
  id: string
  name: string
  kind: 'builtin' | 'agent'
  builtin: string | null
  trigger: Trigger
  brief: string
  toolkits: string[]
  mode: 'shadow' | 'direct'
  status: 'active' | 'paused'
  created_by: 'code' | 'ui' | 'ka'
  created_at: string
  last_checkin: string | null
  last_run: TaskRun | null
  approved: number
  rejected: number
}
export type NewLoop = { name: string; brief: string; trigger: Trigger; toolkits: string[] }
/** One thing Ka reads in an onboarding job (basics, a file, an assistant's export). */
export type PartState = 'waiting' | 'reading' | 'done' | 'failed'
export type IntakeJob = {
  id: string
  kind: 'documents' | 'memory' | 'onboarding'
  status: 'queued' | 'running' | 'done' | 'failed'
  step: string
  message: string
  result: {
    cards?: number
    jobs?: number
    highlights?: number
    memories?: number
    skipped?: string[]
    warnings?: string[]
    parts?: { label: string; state: PartState }[]
  }
  created_at: string
}
export type ActivityRow = {
  id: number
  at: string
  kind: 'read' | 'change' | 'pending' | 'error' | 'sheet' | 'extraction' | 'loop' | 'blocked'
  text: string
  conversation_id: string | null
}
export type OnboardingStatus = { needed: boolean; reason: string }
type GoogleStatus = {
  connected: boolean
  email: string | null
  drive_sync: { at: string; new?: number; skipped?: string[]; error?: string } | null
  sheet: { at: string; ok?: boolean; error?: string } | null
}
export type Settings = {
  models: Record<string, { provider: string; model: string }>
  private_models: { provider: string; model: string }[]
  flags: Record<string, boolean>
  flag_info: { name: string; description: string; on: boolean }[]
  loops_paused: boolean
  google: GoogleIds
}

export type GoogleIds = { drive_folder_id: string | null; sheet_id: string | null }

export const keys = {
  conversations: ['conversations'] as const,
  pending: ['pending'] as const,
  activity: ['activity'] as const,
  settings: ['settings'] as const,
  onboarding: ['onboarding'] as const,
  google: ['google'] as const,
  intake: (id: string) => ['intake', id] as const,
  auth: ['auth'] as const,
  loops: ['loops'] as const,
  runs: (id: string) => ['loops', id, 'runs'] as const,
}

const post = (path: string, body?: unknown) =>
  call<Record<string, unknown>>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  conversations: () => call<ConversationRow[]>('/conversations'),
  conversation: (id: string) => call<{ id: string; items: HistoryItem[] }>(`/conversations/${id}`),
  pending: () => call<PendingRow[]>('/pending'),
  approvePending: (id: number, selected?: string[]) =>
    post(`/pending/${id}/approve`, selected ? { selected } : undefined) as Promise<{ result: string }>,
  rejectPending: (id: number) => post(`/pending/${id}/reject`),
  activity: () => call<ActivityRow[]>('/activity'),
  settings: () => call<Settings>('/settings'),
  googleStatus: () => call<GoogleStatus>('/google/status'),
  googleSync: () => call<{ new: number; skipped: string[] }>('/google/sync', { method: 'POST' }),
  googlePush: () => post('/google/push'),
  googleDisconnect: () => post('/google/disconnect'),
  googleSave: (ids: GoogleIds) =>
    call<{ ok: boolean }>('/google/settings', { method: 'PUT', body: JSON.stringify(ids) }),
  onboardingStatus: () => call<OnboardingStatus>('/onboarding/status'),
  intakeJob: (id: string) => call<IntakeJob>(`/intake/${id}`),
  async sendOnboarding(form: FormData): Promise<{ job_id: string }> {
    const res = await fetch('/api/intake/onboarding', { method: 'POST', body: form })
    if (res.status === 401) onUnauthorized()
    if (!res.ok) {
      throw new ApiError(res.status, await readDetail(res))
    }
    return res.json()
  },
  answerApproval: (id: string, approve: boolean) => post(`/approvals/${id}`, { approve }),
  authStatus: () =>
    call<AuthStatus>('/auth/status').then((s) => {
      rememberUser(s.username)
      return s
    }),
  login: (username: string, password: string) => post('/auth/login', { username, password }),
  signup: (username: string, password: string) => post('/auth/signup', { username, password }),
  logout: () => post('/auth/logout'),
  loops: () => call<LoopTask[]>('/loops'),
  createLoop: (body: NewLoop) => post('/loops', body) as Promise<LoopTask>,
  updateLoop: (id: string, body: Partial<Pick<LoopTask, 'status' | 'mode'>>) =>
    call<LoopTask>(`/loops/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteLoop: (id: string) => call<{ ok: boolean }>(`/loops/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  runLoop: (id: string) => post(`/loops/${encodeURIComponent(id)}/run`) as Promise<TaskRun>,
  loopRuns: (id: string) => call<TaskRun[]>(`/loops/${encodeURIComponent(id)}/runs`),
  setLoopsPaused: (paused: boolean) =>
    call<{ paused: boolean }>('/loops/paused', { method: 'PUT', body: JSON.stringify({ paused }) }),
}
