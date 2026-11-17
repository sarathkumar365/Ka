import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys, type PendingRow } from '../../lib/api'

const KIND: Record<PendingRow['type'], string> = { fact: 'Memory fact', preference: 'Preference', rule: 'Rule' }

function Card({ item }: { item: PendingRow }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const done = () => qc.invalidateQueries({ queryKey: keys.pending })
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(item.id) : api.rejectPending(item.id)),
    onSuccess: () => {
      done()
      qc.invalidateQueries({ queryKey: keys.activity })
    },
    onError: (e: Error) => {
      setError(e.message)
      done()
    },
  })
  return (
    <div className="card">
      <div className="eyebrow">{item.old ? `${KIND[item.type]}, replaces an older one` : KIND[item.type]}</div>
      <div>{item.text}</div>
      {item.old && (
        <div className="swap">
          <div>
            <span className="sub">Saved now</span>
            <div style={{ textDecoration: 'line-through', color: 'var(--t3)' }}>{item.old}</div>
          </div>
          <div>
            <span className="sub">Would become</span>
            <div style={{ fontWeight: 500 }}>{item.text}</div>
          </div>
        </div>
      )}
      {item.source && <div className="sub">{item.source}</div>}
      {error && <div className="notice" role="alert">{error}</div>}
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

export function PendingPage() {
  const { data = [], isLoading } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  return (
    <div className="col page">
      <h1>Pending</h1>
      <p className="sub">{data.length ? 'Ka learned these. Nothing is saved until you approve it.' : ''}</p>
      {!isLoading && data.length === 0 && (
        <div>
          <p>Nothing is waiting for you.</p>
          <p className="sub">Ka will ask here when it learns something new.</p>
        </div>
      )}
      {data.map((i) => (
        <Card key={i.id} item={i} />
      ))}
    </div>
  )
}
