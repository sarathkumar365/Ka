import { expect, test } from 'vitest'
import { emptyDraft, hasInput, summaryLine, toForm } from './draft'

test('hasInput ignores blanks and sees files or memory text', () => {
  expect(hasInput(emptyDraft())).toBe(false)
  const blank = { ...emptyDraft(), basics: { name: '  ', where: '', role: '' } }
  expect(hasInput(blank)).toBe(false)
  expect(hasInput({ ...emptyDraft(), files: [new File(['x'], 'r.txt')] })).toBe(true)
  expect(hasInput({ ...emptyDraft(), memory: [{ id: 1, source: 'Claude', text: 'likes tea' }] })).toBe(true)
})

test('toForm omits empty basics and sends memory as a lower-case list', () => {
  const d = { ...emptyDraft(), memory: [{ id: 1, source: 'ChatGPT', text: 'likes tea' }] }
  const form = toForm(d)
  expect(form.get('basics')).toBeNull()
  expect(JSON.parse(String(form.get('memory')))).toEqual([{ source: 'chatgpt', text: 'likes tea' }])
  const withBasics = toForm({ ...emptyDraft(), basics: { name: 'Avery', where: 'Newtown, North, Wonderland', role: '' } })
  expect(JSON.parse(String(withBasics.get('basics')))).toEqual({
    name: 'Avery',
    city: 'Newtown',
    region: 'North',
    country: 'Wonderland',
    role: '',
  })
})

test('summary copy', () => {
  expect(summaryLine({ cards: 5, jobs: 2, highlights: 7, memories: 4 })).toBe(
    '5 card(s) to review: 2 job(s), 7 highlight(s), 4 memory item(s).',
  )
})
