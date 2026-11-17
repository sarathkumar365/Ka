import { afterEach, expect, test, vi } from 'vitest'
import { getTheme, setTheme } from './theme'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

test('defaults to dark, also when storage throws', () => {
  expect(getTheme()).toBe('dark')
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  expect(getTheme()).toBe('dark')
})

test('setTheme persists and sets the attribute', () => {
  setTheme('light')
  expect(getTheme()).toBe('light')
  expect(document.documentElement.dataset.theme).toBe('light')
})
