import { expect, test } from 'vitest'
import { initialState, reduce, type ChatAction } from './state'

const run = (actions: ChatAction[]) => actions.reduce(reduce, initialState)

test('a full turn builds items and walks the phases', () => {
  let s = run([{ type: 'send', text: 'hi' }])
  expect(s.phase).toBe('thinking')
  s = reduce(s, { type: 'conversation', id: 'C-1' })
  s = reduce(s, { type: 'tool_call', name: 'get_jobs', args: {} })
  expect(s.phase).toBe('searching')
  s = reduce(s, { type: 'tool_result', name: 'get_jobs', result: '[]' })
  s = reduce(s, { type: 'approval', approvalId: 'a1', summary: 'S', diff: 'D' })
  expect(s.phase).toBe('waiting')
  s = reduce(s, { type: 'decide', approvalId: 'a1', approve: true })
  s = reduce(s, { type: 'answer', text: 'ok' })
  expect(s.phase).toBe('answering')
  s = reduce(s, { type: 'done' })
  expect(s.phase).toBe('idle')
  expect(s.conversationId).toBe('C-1')
  expect(s.items.map((i) => i.kind)).toEqual(['user', 'tool', 'approval', 'assistant'])
  expect(s.items[1]).toMatchObject({ result: '[]' })
  expect(s.items[2]).toMatchObject({ decision: 'yes' })
})

test('an error becomes a notice and returns to idle', () => {
  const s = run([{ type: 'send', text: 'x' }, { type: 'error', message: 'no credits' }])
  expect(s.phase).toBe('idle')
  expect(s.items.at(-1)).toEqual({ kind: 'notice', text: 'no credits' })
})
