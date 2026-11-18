import { expect, test } from 'vitest'
import { entityMode, entityStyle } from './entityStyle'

test('each phase takes the geometry from the design prototype', () => {
  const thinking = entityStyle('thinking', 0, false)
  expect([thinking.l, thinking.t, thinking.w, thinking.h, thinking.r, thinking.bw]).toEqual([
    '18px',
    'calc(100% - 62px)',
    '20px',
    '20px',
    '10px',
    '3px',
  ])
  expect(thinking.bc).toBe('transparent') // ThinkingRing draws the ring instead
  expect(entityStyle('searching', 0, false).l).toBe('20px')
  expect(entityStyle('searching', 0, true).l).toBe('calc(100% - 64px)')
  expect(entityStyle('searching', 0, true).tr).toContain('left 900ms ease-in-out')
  expect(entityStyle('waiting', 0, false).sh).toBe('0 0 0 5px var(--lapis-wash)')
  expect(entityStyle('typing', 0, false).w).toBe('100%')
  expect(entityStyle('docked', 0, false).w).toBe('24px')
})

test('the empty blob changes shape every beat', () => {
  expect(entityStyle('empty', 1, false).r).not.toBe(entityStyle('empty', 2, false).r)
  expect(entityStyle('empty', 1, false).tf).toBe('scale(1.025)')
})

test('typing only applies on the empty home', () => {
  expect(entityMode('idle', false, true)).toBe('typing')
  expect(entityMode('idle', true, true)).toBe('docked')
  expect(entityMode('thinking', false, true)).toBe('thinking')
})
