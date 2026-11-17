import { expect, test } from 'vitest'
import { canApprove, toggleItem } from './bundle'

test('toggleItem adds and removes', () => {
  expect(toggleItem(['i1'], 'i2')).toEqual(['i1', 'i2'])
  expect(toggleItem(['i1', 'i2'], 'i1')).toEqual(['i2'])
})

test('canApprove needs ready, unblocked, and the job line ticked', () => {
  const card = { ready: true, blocked: null, section: 'job', items: [{ id: 'i1' }, { id: 'i2' }] }
  expect(canApprove(card, ['i1', 'i2'])).toBe(true)
  expect(canApprove(card, ['i2'])).toBe(false)
  expect(canApprove({ ...card, ready: false }, ['i1'])).toBe(false)
  expect(canApprove({ ...card, blocked: 'no start date found' }, ['i1'])).toBe(false)
  expect(canApprove({ ...card, section: 'highlights' }, ['i2'])).toBe(true)
})
