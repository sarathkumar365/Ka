import { expect, test } from 'vitest'
import { emptyState } from './emptyState'

test('setup card only when the server says onboarding is needed', () => {
  expect(emptyState(undefined)).toBe('ask') // loading or failed: no flash
  expect(emptyState({ needed: false, reason: 'has_data' })).toBe('ask')
  expect(emptyState({ needed: false, reason: 'pending' })).toBe('ask')
  expect(emptyState({ needed: true, reason: 'first_run' })).toBe('setup')
})
