export class ApiError extends Error {
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
export type HistoryItem =
  | { kind: 'user' | 'assistant'; text: string }
  | { kind: 'tool'; name: string; args: Record<string, unknown>; result: string | null }
export type PendingRow = {
  id: number
  type: 'fact' | 'preference' | 'rule'
  text: string
  old: string | null
  source: string | null
  created_at: string
}
export type ActivityRow = {
  id: number
  at: string
  kind: 'read' | 'change' | 'pending' | 'error'
  text: string
  conversation_id: string | null
}
export type Settings = {
  models: Record<string, { provider: string; model: string }>
  flags: Record<string, boolean>
}

export const keys = {
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversation', id] as const,
  pending: ['pending'] as const,
  activity: ['activity'] as const,
  settings: ['settings'] as const,
}

const post = (path: string, body?: unknown) =>
  call<Record<string, unknown>>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  conversations: () => call<ConversationRow[]>('/conversations'),
  conversation: (id: string) => call<{ id: string; items: HistoryItem[] }>(`/conversations/${id}`),
  pending: () => call<PendingRow[]>('/pending'),
  approvePending: (id: number) => post(`/pending/${id}/approve`) as Promise<{ result: string }>,
  rejectPending: (id: number) => post(`/pending/${id}/reject`),
  activity: () => call<ActivityRow[]>('/activity'),
  settings: () => call<Settings>('/settings'),
  answerApproval: (id: string, approve: boolean) => post(`/approvals/${id}`, { approve }),
}
