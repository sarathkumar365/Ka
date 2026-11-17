import { expect, test } from 'vitest'
import { nextAssistant, toItems } from './memory'

test('sends only filled boxes, lower-cased', () => {
  const entries = [
    { id: 1, source: 'Claude', text: 'likes tea' },
    { id: 2, source: 'ChatGPT', text: '   ' },
  ]
  expect(toItems(entries)).toEqual([{ source: 'claude', text: 'likes tea' }])
})

test('next box picks an unused assistant', () => {
  expect(nextAssistant([{ id: 1, source: 'Claude', text: '' }])).toBe('ChatGPT')
  expect(nextAssistant([])).toBe('Claude')
})
