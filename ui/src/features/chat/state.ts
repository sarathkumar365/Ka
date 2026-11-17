export type ChatEvent =
  | { type: 'conversation'; id: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: string }
  | { type: 'approval'; approvalId: string; summary: string; diff: string }
  | { type: 'answer'; text: string }
  | { type: 'stopped'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

export type ChatItem =
  | { kind: 'user' | 'assistant'; text: string }
  | { kind: 'tool'; name: string; args: Record<string, unknown>; result?: string }
  | { kind: 'approval'; approvalId: string; summary: string; diff: string; decision?: 'yes' | 'no' }
  | { kind: 'notice'; text: string }

export type Phase = 'idle' | 'thinking' | 'searching' | 'answering' | 'waiting'
export type ChatState = { items: ChatItem[]; phase: Phase; conversationId: string | null }
export type ChatAction =
  | ChatEvent
  | { type: 'send'; text: string }
  | { type: 'decide'; approvalId: string; approve: boolean }
  | { type: 'load'; conversationId: string | null; items: ChatItem[] }

export const initialState: ChatState = { items: [], phase: 'idle', conversationId: null }

export function reduce(state: ChatState, a: ChatAction): ChatState {
  const add = (item: ChatItem, phase: Phase = state.phase): ChatState => ({
    ...state,
    items: [...state.items, item],
    phase,
  })
  switch (a.type) {
    case 'load':
      return { items: a.items, phase: 'idle', conversationId: a.conversationId }
    case 'send':
      return add({ kind: 'user', text: a.text }, 'thinking')
    case 'conversation':
      return { ...state, conversationId: a.id }
    case 'tool_call':
      return add({ kind: 'tool', name: a.name, args: a.args }, 'searching')
    case 'tool_result': {
      const i = state.items.findLastIndex((x) => x.kind === 'tool' && x.name === a.name && x.result === undefined)
      if (i < 0) return state
      const items = state.items.slice()
      items[i] = { ...(items[i] as Extract<ChatItem, { kind: 'tool' }>), result: a.result }
      return { ...state, items, phase: 'thinking' }
    }
    case 'approval':
      return add({ kind: 'approval', approvalId: a.approvalId, summary: a.summary, diff: a.diff }, 'waiting')
    case 'decide':
      return {
        ...state,
        phase: 'thinking',
        items: state.items.map((x) =>
          x.kind === 'approval' && x.approvalId === a.approvalId ? { ...x, decision: a.approve ? 'yes' : 'no' } : x,
        ),
      }
    case 'answer':
      return add({ kind: 'assistant', text: a.text }, 'answering')
    case 'stopped':
      return add({ kind: 'notice', text: a.text }, 'idle')
    case 'error':
      return add({ kind: 'notice', text: a.message }, 'idle')
    case 'done':
      return { ...state, phase: 'idle' }
  }
}
