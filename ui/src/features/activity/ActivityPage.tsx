import { useQuery } from '@tanstack/react-query'
import { api, keys } from '../../lib/api'
import { groupByDay } from './group'

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: false })

export function ActivityPage() {
  const { data = [], isLoading } = useQuery({ queryKey: keys.activity, queryFn: api.activity })
  return (
    <div className="col page">
      <div className="pagehead">
        <h1>Activity</h1>
        <div className="pagesub">Everything Ka looked at or changed, in order.</div>
      </div>
      {!isLoading && data.length === 0 && <p className="hint">Nothing yet.</p>}
      {groupByDay(data, new Date()).map((g) => (
        <section key={g.label} className="day">
          <h2>{g.label}</h2>
          <ul className="log">
            {g.rows.map((r) => (
              <li key={r.id} data-kind={r.kind}>
                <span className="t">{time(r.at)}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
