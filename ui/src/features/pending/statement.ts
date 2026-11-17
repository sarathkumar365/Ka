import type { StatementRow } from '../../lib/api'

/** Why a statement card cannot be imported, or null when it can. */
export function importBlocker(card: Pick<StatementRow, 'checks' | 'already_imported'>): string | null {
  if (card.already_imported) return 'Already imported. Skip this copy.'
  if (card.checks.length) return 'Checks failed, so nothing can be imported.'
  return null
}
