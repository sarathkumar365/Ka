import { expect, test } from 'vitest'
import { approach, arcs, partAlpha, settleFactor } from './ring'

test('approach eases toward the target and snaps when close', () => {
  expect(approach(0, 100, 0.085)).toBeCloseTo(8.5)
  expect(approach(99.995, 100, 0.085)).toBe(100)
})

test('arcs split the ring evenly from 12 o clock, gaps included', () => {
  const a = arcs(3, 0.2)
  expect(a).toHaveLength(3)
  expect(a[0].start).toBeCloseTo(-Math.PI / 2 + 0.1)
  const span = (2 * Math.PI) / 3
  expect(a[1].start - a[0].start).toBeCloseTo(span)
  expect(a[0].end - a[0].start).toBeCloseTo(span - 0.2)
  expect(arcs(0, 0.2)).toEqual([])
})

test('part brightness follows real state', () => {
  expect(partAlpha('done', 0)).toBe(1)
  expect(partAlpha('waiting', 0)).toBeLessThan(partAlpha('reading', 0))
  expect(partAlpha('failed', 0)).toBeLessThan(partAlpha('waiting', 0))
})

test('settle factor gives the same motion per second at any refresh rate', () => {
  const at60 = 1 - (1 - settleFactor(0.085, 1000 / 60)) ** 60
  const at120 = 1 - (1 - settleFactor(0.085, 1000 / 120)) ** 120
  expect(at120).toBeCloseTo(at60, 6)
})
