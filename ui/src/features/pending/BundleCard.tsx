import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { Decided } from './PendingPage'
import { api, keys, type BundleRow } from '../../lib/api'
import { canApprove, toggleItem } from './bundle'

const KIND: Record<BundleRow['section'], string> = {
  basics: 'Basics',
  education: 'Education',
  domains: 'Domains',
  job: 'Job',
  highlights: 'More highlights',
  categories: 'Spending categories',
  types: 'Transaction types',
}

export function BundleCard({ card, onDone }: { card: BundleRow; onDone: Decided }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState(() => card.items.filter((i) => i.selected).map((i) => i.id))
  const [error, setError] = useState<string | null>(null)
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.pending })
    qc.invalidateQueries({ queryKey: keys.activity })
  }
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(card.id, selected) : api.rejectPending(card.id)),
    onSuccess: (_, approve) => {
      onDone(approve ? 'yes' : 'no')
      refresh()
    },
    onError: (e: Error) => {
      setError(e.message)
      refresh()
    },
  })
  const ok = canApprove(card, selected)
  return (
    <div className="card">
      <div className="kind">{KIND[card.section]}</div>
      <div className="ptext">{card.title}</div>
      {card.blocked && <div className="notice">{card.blocked}. Reject this card and tell Ka the fix in chat.</div>}
      {!card.ready && !card.blocked && <div className="notice">Needs Domains first. Approve or reject that card.</div>}
      <ul className="lines">
        {card.items.map((it, i) => (
          <li key={it.id}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(it.id)}
                disabled={card.section === 'job' && i === 0}
                onChange={() => setSelected(toggleItem(selected, it.id))}
              />
              <span>
                <span className={i === 0 && card.section === 'job' ? 'strong' : ''}>{it.label}</span>
                {it.detail && <span className="sub tags">{it.detail}</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ gap: 8 }}>
        <button className="primary" disabled={!ok || act.isPending} onClick={() => act.mutate(true)}>
          Approve selected
        </button>
        <button className="secondary" disabled={act.isPending} onClick={() => act.mutate(false)}>
          Reject
        </button>
      </div>
    </div>
  )
}
