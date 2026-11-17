import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys, type StatementRow } from '../../lib/api'
import { importBlocker } from './statement'

export function StatementCard({ card }: { card: StatementRow }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.pending })
    qc.invalidateQueries({ queryKey: keys.activity })
  }
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(card.id) : api.rejectPending(card.id)),
    onSuccess: refresh,
    onError: (e: Error) => {
      setError(e.message)
      refresh()
    },
  })
  const blocker = importBlocker(card)
  return (
    <div className="card">
      <div className="eyebrow">Statement from Drive</div>
      <div style={{ fontWeight: 500 }}>{card.file}</div>
      <div className="sub">
        {card.account}, {card.period_start} to {card.period_end}, {card.rows} rows
      </div>
      <div className="row" style={{ gap: 16 }}>
        <span>
          In <span className="mono">{card.money_in}</span>
        </span>
        <span>
          Out <span className="mono">{card.money_out}</span>
        </span>
      </div>
      {card.checks.map((c) => (
        <div key={c} className="sub">
          {c}
        </div>
      ))}
      {card.unknown_merchants > 0 && <div className="sub">{card.unknown_merchants} merchants without a category</div>}
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
