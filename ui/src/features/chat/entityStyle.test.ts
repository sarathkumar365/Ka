import { expect, test } from 'vitest'
import { entityMode, entityStyle } from './entityStyle'

test('typing only applies on the empty home', () => {
  expect(entityMode('idle', false, true)).toBe('typing')
  expect(entityMode('idle', true, true)).toBe('docked')
  expect(entityMode('thinking', false, true)).toBe('thinking')
})

test('entity tops are plain percentages, so a keyboard opening never starts a transition', () => {
  // the bottom inset (home bar or keyboard) lives on .entity-stage; a var() here would change the
  // computed top whenever --kb changes and the entity would glide behind the composer
  for (const mode of ['typing', 'thinking', 'searching', 'waiting', 'docked'] as const)
    expect(entityStyle(mode, 0, false).t).not.toContain('var(')
  expect(entityStyle('typing', 0, false).t).toBe('calc(100% - 80px)')
})
