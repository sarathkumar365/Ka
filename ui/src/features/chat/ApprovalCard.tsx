export function ApprovalCard({
  summary,
  diff,
  decision,
  onDecide,
}: {
  summary: string
  diff: string
  decision?: 'yes' | 'no'
  onDecide: (approve: boolean) => void
}) {
  return (
    <div className="card approval">
      <div className="eyebrow">Needs your approval</div>
      <div style={{ fontWeight: 500 }}>{summary}</div>
      {diff && <pre className="mono diff">{diff}</pre>}
      {decision ? (
        <div className="decided">{decision === 'yes' ? 'You approved this.' : 'You declined this. Nothing was changed.'}</div>
      ) : (
        <>
          <div className="hint">Nothing is saved until you say yes.</div>
          <div className="row" style={{ gap: 8 }}>
            <button className="primary" onClick={() => onDecide(true)}>
              Yes
            </button>
            <button className="secondary" onClick={() => onDecide(false)}>
              No
            </button>
          </div>
        </>
      )}
    </div>
  )
}
