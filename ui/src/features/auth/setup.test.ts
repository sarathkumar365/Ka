import { expect, test } from 'vitest'
import { detailText } from '../../lib/api'
import { setupProblem } from './rules'

const rules = { min_password: 10, username_rule: '^[a-z][a-z0-9_-]{2,31}$' }
const pw = 'x'.repeat(10)

test('account form says why it cannot be sent, using the server rules', () => {
  expect(setupProblem(rules, '', pw, pw)).toMatch(/Choose a username/)
  expect(setupProblem(rules, '1me', pw, pw)).toMatch(/starting with a letter/)
  expect(setupProblem(rules, 'me', pw, pw)).toMatch(/3 to 32/)
  expect(setupProblem(rules, 'avery', 'short', 'short')).toMatch(/10 characters/)
  expect(setupProblem(rules, 'avery', pw, 'y'.repeat(10))).toMatch(/differ/)
  expect(setupProblem(rules, 'avery', pw, pw)).toBeNull()
})

test('a failed body check shows its message, not [object Object]', () => {
  const body = { detail: [{ msg: 'String should have at most 256 characters' }] }
  expect(detailText(body, 'Unprocessable')).toBe('String should have at most 256 characters')
  expect(detailText({ detail: 'wrong username or password' }, 'x')).toBe('wrong username or password')
  expect(detailText(null, 'Bad Gateway')).toBe('Bad Gateway')
})
