import { expect, test } from 'vitest'
import { providerName } from './provider'

test('provider ids read as names', () => {
  expect(providerName('openai')).toBe('OpenAI')
  expect(providerName(undefined)).toBe('your model provider')
  expect(providerName('acme')).toBe('acme')
})
