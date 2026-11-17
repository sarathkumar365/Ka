import { useQuery } from '@tanstack/react-query'
import { api, keys } from '../../lib/api'
import { groupByDay } from './group'

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })

export function ActivityPage() {
  const { data = [], isLoading } = useQuery({ queryKey: keys.activity, queryFn: api.activity })
  return (
    <div className="col page">
      <h1>Activity</h1>
      <p className="sub">Everything Ka looked at or changed, in order.</p>
      {!isLoading && data.length === 0 && <p className="sub">Nothing yet.</p>}
      {groupByDay(data, new Date()).map((g) => (
        <section key={g.label}>
          <h2>{g.label}</h2>
          <ul className="log">
            {g.rows.map((r) => (
              <li key={r.id} data-kind={r.kind}>
                <span className="mono t">{time(r.at)}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
