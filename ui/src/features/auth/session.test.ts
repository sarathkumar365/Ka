import { afterEach, expect, test } from 'vitest'
import { capture, registerDraft, rememberUser, saveReturn, takeDraft, takeReturn } from './session'

afterEach(() => {
  sessionStorage.clear()
  registerDraft(null)
  rememberUser(null)
})

test('return target survives one read', () => {
  saveReturn('/chat/C-1', 'half typed', 'avery')
  expect(takeReturn('avery')).toEqual({ path: '/chat/C-1', draft: 'half typed' })
  expect(takeReturn('avery')).toBeNull()
})

test('an expired session keeps the unsent message for after login', () => {
  rememberUser('avery')
  registerDraft(() => 'x')
  capture('/chat/C-2')
  expect(takeReturn('avery')).toEqual({ path: '/chat/C-2', draft: 'x' })
})

test('the draft is handed to the composer once, to the same account', () => {
  saveReturn('/chat', 'hello', 'avery')
  takeReturn('avery')
  rememberUser('avery')
  expect(takeDraft()).toBe('hello')
  expect(takeDraft()).toBe('')
})

test('login and sign-up paths are never a return target', () => {
  rememberUser('avery')
  capture('/login')
  expect(takeReturn('avery')).toEqual({ path: '/chat', draft: '' })
})

test('a message sent just as the session ended is kept, though the composer was cleared', () => {
  rememberUser('avery')
  registerDraft(() => '')
  capture('/chat/C-3', 'how much on groceries?')
  expect(takeReturn('avery')).toEqual({ path: '/chat/C-3', draft: 'how much on groceries?' })
})

test('a draft saved by one account is not restored for another', () => {
  saveReturn('/chat/C-1', 'half a message', 'avery')
  expect(takeReturn('blake')).toBeNull()
  rememberUser('blake')
  expect(takeDraft()).toBe('')
})
