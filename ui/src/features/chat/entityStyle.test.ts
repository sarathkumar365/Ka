import { expect, test } from 'vitest'
import { entityMode } from './entityStyle'

test('typing only applies on the empty home', () => {
  expect(entityMode('idle', false, true)).toBe('typing')
  expect(entityMode('idle', true, true)).toBe('docked')
  expect(entityMode('thinking', false, true)).toBe('thinking')
})
