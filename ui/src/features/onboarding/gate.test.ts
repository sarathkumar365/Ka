import { renderHook } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { OnboardingStatus } from '../../lib/api'
import { shouldRedirect, useFirstRunRedirect } from './gate'

const needed: OnboardingStatus = { needed: true, reason: 'first_run' }

test('redirects only when needed and not already on onboarding', () => {
  expect(shouldRedirect(undefined, '/chat')).toBe(false) // loading or request failed
  expect(shouldRedirect({ needed: false, reason: 'has_data' }, '/chat')).toBe(false)
  expect(shouldRedirect(needed, '/onboarding')).toBe(false)
  expect(shouldRedirect(needed, '/onboarding/x')).toBe(false)
  for (const p of ['/chat', '/chat/C-1', '/pending', '/settings']) expect(shouldRedirect(needed, p)).toBe(true)
})

test('the redirect fires once per page load, so links keep working during onboarding', () => {
  const nav = vi.fn()
  const { rerender } = renderHook(({ status, path }) => useFirstRunRedirect(status, path, nav), {
    initialProps: { status: undefined as OnboardingStatus | undefined, path: '/chat' },
  })
  expect(nav).not.toHaveBeenCalled() // still loading
  rerender({ status: needed, path: '/chat' })
  expect(nav).toHaveBeenCalledTimes(1)
  expect(nav).toHaveBeenCalledWith('/onboarding', { replace: true })
  rerender({ status: needed, path: '/pending' }) // owner clicks Open Pending
  expect(nav).toHaveBeenCalledTimes(1)
})

test('a failed status request never redirects, even when it later settles', () => {
  const nav = vi.fn()
  const { rerender } = renderHook(({ status }) => useFirstRunRedirect(status, '/chat', nav), {
    initialProps: { status: undefined as OnboardingStatus | undefined },
  })
  rerender({ status: undefined })
  expect(nav).not.toHaveBeenCalled()
})
