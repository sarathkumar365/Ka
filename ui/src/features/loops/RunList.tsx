import { useQuery } from '@tanstack/react-query'
import { api, keys } from '../../lib/api'

export function RunList({ taskId }: { taskId: string }) {
  const { data = [] } = useQuery({ queryKey: keys.runs(taskId), queryFn: () => api.loopRuns(taskId) })
  if (!data.length) return <div className="hint">No runs yet.</div>
  return (
    <ul className="runs">
      {data.map((r) => (
        <li key={r.id}>
          <span>{r.started_at.slice(0, 16).replace('T', ' ')}</span> <span>{r.status}</span>
          {r.reason && <span> ({r.reason})</span>}
          <span className="mono">
            {' '}
            {r.model_calls} model, {r.tool_calls} tool, ${r.cost_usd}
          </span>
        </li>
      ))}
    </ul>
  )
}
