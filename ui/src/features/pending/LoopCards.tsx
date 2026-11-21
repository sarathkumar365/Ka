import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { type AlertRow, api, keys, type ToolWriteRow } from '../../lib/api'
import type { Decided } from './PendingPage'

function useDecide(id: number, onDone: Decided) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(id) : api.rejectPending(id)),
    onSuccess: (_, approve) => {
      onDone(approve ? 'yes' : 'no')
      qc.invalidateQueries({ queryKey: keys.pending })
      qc.invalidateQueries({ queryKey: keys.activity })
    },
    onError: (e: Error) => {
      setError(e.message)
      qc.invalidateQueries({ queryKey: keys.pending })
    },
  })
  return { act, error }
}

/** A change a scheduled task wanted to make (shadow mode). Yes re-runs it on current data. */
export function ToolWriteCard({ card, onDone }: { card: ToolWriteRow; onDone: Decided }) {
  const { act, error } = useDecide(card.id, onDone)
  return (
    <div className="card">
      <div className="kind">A scheduled task wants to make a change</div>
      <div className="ptext">{card.summary}</div>
      {card.diff && <div className="diff">{card.diff}</div>}
      {card.after_untrusted && (
        <div className="notice">The task read outside content (a web page or a statement) before asking.</div>
      )}
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ gap: 8 }}>
        <button className="primary" disabled={act.isPending} onClick={() => act.mutate(true)}>
          Approve
        </button>
        <button className="secondary" disabled={act.isPending} onClick={() => act.mutate(false)}>
          Reject
        </button>
      </div>
    </div>
  )
}

/** A stopped or missed run, or a card that has waited too long. Either button dismisses it. */
export function AlertCard({ card, onDone }: { card: AlertRow; onDone: Decided }) {
  const { act, error } = useDecide(card.id, onDone)
  return (
    <div className="card">
      <div className="kind">Alert</div>
      <div className="ptext">{card.title}</div>
      {card.detail && <div className="src">{card.detail}</div>}
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ gap: 8 }}>
        <button className="primary" disabled={act.isPending} onClick={() => act.mutate(true)}>
          Got it
        </button>
      </div>
    </div>
  )
}
