import { expect, test } from 'vitest'
import { ringPath } from './ringPath'

test('the ring wobbles and the arc drifts over time, and holds still under reduced motion', () => {
  expect(ringPath(1, false).ring).not.toBe(ringPath(2, false).ring)
  expect(ringPath(1, false).arc).not.toBe(ringPath(2, false).arc)
  expect(ringPath(1, true)).toEqual(ringPath(2, true))
})
