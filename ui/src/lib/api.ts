class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { 'content-type': 'application/json' } : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, String(detail))
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
type PendingRow = MemoryRow | BundleRow | StatementRow
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
  kind: 'read' | 'change' | 'pending' | 'error'
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
  flags: Record<string, boolean>
}

export const keys = {
  conversations: ['conversations'] as const,
  pending: ['pending'] as const,
  activity: ['activity'] as const,
  settings: ['settings'] as const,
  onboarding: ['onboarding'] as const,
  google: ['google'] as const,
  intake: (id: string) => ['intake', id] as const,
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
  onboardingStatus: () => call<OnboardingStatus>('/onboarding/status'),
  intakeJob: (id: string) => call<IntakeJob>(`/intake/${id}`),
  async sendOnboarding(form: FormData): Promise<{ job_id: string }> {
    const res = await fetch('/api/intake/onboarding', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = res.statusText
      try {
        detail = (await res.json()).detail ?? detail
      } catch {
        /* keep statusText */
      }
      throw new ApiError(res.status, String(detail))
    }
    return res.json()
  },
  answerApproval: (id: string, approve: boolean) => post(`/approvals/${id}`, { approve }),
}
