import { expect, test } from 'vitest'
import { importBlocker } from './statement'

test('blocks already imported and failed checks, allows a clean statement', () => {
  expect(importBlocker({ checks: [], already_imported: false })).toBeNull()
  expect(importBlocker({ checks: [], already_imported: true })).toMatch(/Already imported/)
  expect(importBlocker({ checks: ['balance row 3: off by 0.01'], already_imported: false })).toMatch(/Checks failed/)
})
