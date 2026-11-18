import type { Phase } from './state'

type EntityMode = 'empty' | 'thinking' | 'searching' | 'waiting' | 'docked'

export function entityMode(phase: Phase, hasItems: boolean): EntityMode {
  if (!hasItems && phase === 'idle') return 'empty'
  if (phase === 'thinking') return 'thinking'
  if (phase === 'searching') return 'searching'
  if (phase === 'idle') return 'docked'
  return 'waiting'
}

/** The lapis shape from the design. Position and size come from CSS per data-mode. */
export function Entity({ mode }: { mode: EntityMode }) {
  return <div className="entity" data-mode={mode} role="img" aria-label="Ka" />
}
