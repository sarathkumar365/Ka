import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, keys, type MemoryRow, type PendingRow } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { BundleCard } from './BundleCard'
import { StatementCard } from './StatementCard'

export type Decided = (dir: 'yes' | 'no') => void

const KIND: Record<MemoryRow['type'], string> = { fact: 'Memory fact', preference: 'Preference', rule: 'Rule' }
const EXIT_MS = 460 // longest card transition (transform 420ms) plus a frame

function Card({ item, onDone }: { item: MemoryRow; onDone: Decided }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const done = () => qc.invalidateQueries({ queryKey: keys.pending })
  const act = useMutation({
    mutationFn: (approve: boolean) => (approve ? api.approvePending(item.id) : api.rejectPending(item.id)),
    onSuccess: (_, approve) => {
      onDone(approve ? 'yes' : 'no')
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
      <div className="kind">{item.old ? `${KIND[item.type]}, replaces an older one` : KIND[item.type]}</div>
      <div className="ptext">{item.text}</div>
      {item.old && (
        <div className="swap">
          <div>
            <span>Saved now</span>
            <span style={{ color: 'var(--t2)' }}>{item.old}</span>
          </div>
          <div>
            <span>Would become</span>
            <span style={{ fontWeight: 500 }}>{item.text}</span>
          </div>
        </div>
      )}
      {item.source && <div className="src">{item.source}</div>}
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

function Any({ row, onDone }: { row: PendingRow; onDone: Decided }) {
  if (row.kind === 'bundle') return <BundleCard card={row} onDone={onDone} />
  if (row.kind === 'statement') return <StatementCard card={row} onDone={onDone} />
  return <Card item={row} onDone={onDone} />
}

/**
 * One card at a time, stacked in one grid cell (design): a yes leaves to the right, a no to the
 * left, and the next card rises into place. A decided card is kept for its exit after the list
 * refetch has already dropped it.
 */
export function PendingPage() {
  const { data = [], isLoading } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  const [exits, setExits] = useState<{ row: PendingRow; dir: 'yes' | 'no' }[]>([])
  const [decided, setDecided] = useState(0) // cards decided since this page opened, for "2 of 5"
  // arriving from onboarding, the page fades in behind the ring (see .page.arrive)
  const from = useLocation().state?.from
  const [arrive] = useState(() => from === 'onboarding')
  // Decided ids stay out of the queue for good (ids are never reused), however slow the refetch;
  // the exit element itself only lives for its animation.
  const [gone, setGone] = useState<ReadonlySet<number>>(new Set())
  const queue = data.filter((r) => !gone.has(r.id))
  const decide = (row: PendingRow) => (dir: 'yes' | 'no') => {
    setDecided((n) => n + 1)
    setGone((g) => new Set(g).add(row.id))
    setExits((x) => [...x, { row, dir }])
    window.setTimeout(() => setExits((x) => x.filter((e) => e.row.id !== row.id)), EXIT_MS)
  }
  const sub = isLoading
    ? ''
    : queue.length
      ? `${decided + 1} of ${decided + queue.length}. Ka inferred these and needs a yes or no.`
      : 'All caught up.'
  return (
    <div className={`col page${arrive ? ' arrive' : ''}`}>
      <div className="pagehead">
        <h1>Pending</h1>
        <div className="pagesub">{sub}</div>
      </div>
      <div className="pstack">
        {exits.map((e) => (
          <div key={e.row.id} className="pcard" data-pos={e.dir} inert>
            <Any row={e.row} onDone={() => {}} />
          </div>
        ))}
        {queue.map((r, i) => (
          <div key={r.id} className="pcard" data-pos={i === 0 ? 'current' : 'next'} inert={i > 0}>
            <Any row={r} onDone={decide(r)} />
          </div>
        ))}
        {!isLoading && queue.length === 0 && (
          <div className="cleared">
            <Icon name="check" />
            <div>Nothing is waiting for you.</div>
            <div className="hint">Ka will ask here when it learns something new.</div>
          </div>
        )}
      </div>
    </div>
  )
}
