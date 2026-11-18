import type { OnboardingStatus } from '../../lib/api'

/** What the empty chat home shows. Unknown status (loading, failed) stays neutral so nothing flashes. */
export function emptyState(status: OnboardingStatus | undefined): 'setup' | 'ask' {
  return status?.needed ? 'setup' : 'ask'
}
