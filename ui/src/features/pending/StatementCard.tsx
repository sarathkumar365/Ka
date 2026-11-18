import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { Decided } from './PendingPage'
import { api, keys, type StatementRow } from '../../lib/api'
import { importBlocker } from './statement'

export function StatementCard({ card, onDone }: { card: StatementRow; onDone: Decided }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.pending })
    qc.invalidateQueries({ queryKey: keys.activity })
  }
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(card.id) : api.rejectPending(card.id)),
    onSuccess: (_, approve) => {
      onDone(approve ? 'yes' : 'no')
      refresh()
    },
    onError: (e: Error) => {
      setError(e.message)
      refresh()
    },
  })
  const blocker = importBlocker(card)
  return (
    <div className="card">
      <div className="kind">Statement from Drive</div>
      <div className="ptext">{card.file}</div>
      <div className="stats">
        <div>
          <span>Account</span>
          <span>{card.account}</span>
        </div>
        <div>
          <span>Rows</span>
          <span>{card.rows}</span>
        </div>
        <div>
          <span>Money in</span>
          <span>{card.money_in}</span>
        </div>
        <div>
          <span>Money out</span>
          <span>{card.money_out}</span>
        </div>
        <div>
          <span>Dates</span>
          <span>
            {card.period_start} to {card.period_end}
          </span>
        </div>
      </div>
      {card.checks.map((c) => (
        <div key={c} className="src">
          {c}
        </div>
      ))}
      {card.unknown_merchants > 0 && <div className="src">{card.unknown_merchants} merchants without a category</div>}
      {blocker && <div className="notice">{blocker}</div>}
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ gap: 8 }}>
        <button className="primary" disabled={!!blocker || act.isPending} onClick={() => act.mutate(true)}>
          Import
        </button>
        <button className="secondary" disabled={act.isPending} onClick={() => act.mutate(false)}>
          Skip
        </button>
      </div>
    </div>
  )
}
