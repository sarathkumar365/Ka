import { expect, test } from 'vitest'
import { pt, shapePath, spring } from './entityShape'

const circle = { x: 100, y: 100, hw: 50, hh: 50, r: 50 }

test('the outline walks the whole perimeter and the wobble actually moves it', () => {
  const top = pt(circle, 0.875) // last quarter arc ends back at the top
  expect(Math.hypot(top[0] - 100, top[1] - 100)).toBeCloseTo(50, 5)
  const still = shapePath(circle, 0, 0)
  expect(still.startsWith('M') && still.endsWith('Z')).toBe(true)
  expect(shapePath(circle, 0.1, 0)).not.toBe(still)
  expect(shapePath(circle, 0.1, 1)).not.toBe(shapePath(circle, 0.1, 0)) // it changes over time
})

test('the spring settles on its target and snaps under reduced motion', () => {
  const s = { x: 0, v: 0 }
  for (let i = 0; i < 300; i++) spring(s, 10, 1 / 60, 260, 24, false)
  expect(s.x).toBeCloseTo(10, 2)
  const r = { x: 0, v: 3 }
  spring(r, 5, 1 / 60, 260, 24, true)
  expect(r).toEqual({ x: 5, v: 0 })
})
