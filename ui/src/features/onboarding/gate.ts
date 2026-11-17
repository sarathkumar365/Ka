import { useEffect, useRef } from 'react'
import type { OnboardingStatus } from '../../lib/api'

/** Redirect to onboarding only when the server says it is needed and we are not already there. */
export function shouldRedirect(status: OnboardingStatus | undefined, pathname: string): boolean {
  return status?.needed === true && !pathname.startsWith('/onboarding')
}

/**
 * Start on onboarding at most once per page load. Later navigation (Open Pending, the bell,
 * the sidebar) must work while the owner is still setting up. Does nothing while the status is
 * unknown or when the request failed.
 */
export function useFirstRunRedirect(
  status: OnboardingStatus | undefined,
  pathname: string,
  nav: (to: string, opts: { replace: boolean }) => void,
): void {
  const decided = useRef(false)
  useEffect(() => {
    if (decided.current || status === undefined) return
    decided.current = true
    if (shouldRedirect(status, pathname)) nav('/onboarding', { replace: true })
  }, [status, pathname, nav])
}
