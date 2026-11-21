import { fetchEventSource } from '@microsoft/fetch-event-source'
import { onUnauthorized } from '../features/auth/session'
import type { ChatEvent } from '../features/chat/state'

type ChatRequest = { conversation_id: string | null; text: string }

class Fatal extends Error {}

function toEvent(name: string, d: Record<string, unknown>): ChatEvent | null {
  switch (name) {
    case 'conversation':
      return { type: 'conversation', id: String(d.id) }
    case 'tool_call':
      return { type: 'tool_call', name: String(d.name), args: (d.args as Record<string, unknown>) ?? {} }
    case 'tool_result':
      return { type: 'tool_result', name: String(d.name), result: String(d.result) }
    case 'approval':
      return { type: 'approval', approvalId: String(d.approval_id), summary: String(d.summary), diff: String(d.diff ?? '') }
    case 'answer':
    case 'stopped':
      return { type: name, text: String(d.text) }
    case 'error':
      return { type: 'error', message: String(d.message) }
    case 'done':
      return { type: 'done' }
    default:
      return null
  }
}

export async function streamChat(
  body: ChatRequest,
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  await fetchEventSource('/api/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal,
    openWhenHidden: true,
    async onopen(res) {
      if (res.status === 401) onUnauthorized(body.text)
      if (!res.ok) {
        let detail = res.statusText
        try {
          detail = (await res.json()).detail ?? detail
        } catch {
          /* keep statusText */
        }
        throw new Fatal(String(detail))
      }
    },
    onmessage(ev) {
      const e = toEvent(ev.event, JSON.parse(ev.data))
      if (e) onEvent(e)
    },
    onerror(err) {
      throw err // never retry: a retry would send the user's message twice
    },
  })
}
