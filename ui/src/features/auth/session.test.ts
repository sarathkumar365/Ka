import { afterEach, expect, test } from 'vitest'
import { capture, registerDraft, saveReturn, takeDraft, takeReturn } from './session'

afterEach(() => {
  sessionStorage.clear()
  registerDraft(null)
})

test('return target survives one read', () => {
  saveReturn('/chat/C-1', 'half typed')
  expect(takeReturn()).toEqual({ path: '/chat/C-1', draft: 'half typed' })
  expect(takeReturn()).toBeNull()
})

test('an expired session keeps the unsent message for after login', () => {
  registerDraft(() => 'x')
  capture('/chat/C-2')
  const back = takeReturn()
  expect(back).toEqual({ path: '/chat/C-2', draft: 'x' })
})

test('the draft is handed to the composer once', () => {
  saveReturn('/chat', 'hello')
  takeReturn()
  expect(takeDraft()).toBe('hello')
  expect(takeDraft()).toBe('')
})

test('login and setup paths are never a return target', () => {
  capture('/login')
  expect(takeReturn()).toEqual({ path: '/chat', draft: '' })
})

test('a message sent just as the session ended is kept, though the composer was cleared', () => {
  registerDraft(() => '')
  capture('/chat/C-3', 'how much on groceries?')
  expect(takeReturn()).toEqual({ path: '/chat/C-3', draft: 'how much on groceries?' })
})
