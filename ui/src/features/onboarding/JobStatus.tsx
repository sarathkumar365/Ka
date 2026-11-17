import type { IntakeJob } from '../../lib/api'

export function JobStatus({ job }: { job?: IntakeJob }) {
  if (!job) return null
  if (job.status === 'failed')
    return (
      <div className="notice" role="alert">
        {job.message}
      </div>
    )
  if (job.status === 'done') {
    const r = job.result
    return (
      <div className="sub">
        Done. {r.cards ?? 0} item{r.cards === 1 ? '' : 's'} waiting in Pending.
        {(r.warnings ?? []).map((w) => (
          <div key={w}>Note: {w}</div>
        ))}
        {(r.skipped ?? []).map((w) => (
          <div key={w}>Skipped: {w}</div>
        ))}
      </div>
    )
  }
  return (
    <div className="sub" aria-live="polite">
      {job.step || 'Working'}…
    </div>
  )
}
