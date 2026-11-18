import { Icon } from '../../lib/icons'

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
  // Once decided, the question folds away and one line with an icon says what happened (design).
  // It says Approved, not Saved: the write can still fail, and that failure arrives as a notice.
  return (
    <div className="card approval" data-decided={decision ?? undefined}>
      {decision ? (
        <div className={`decided ${decision}`}>
          <Icon name={decision === 'yes' ? 'check' : 'dash'} />
          <span>{decision === 'yes' ? `Approved. ${summary}` : 'Left as it was.'}</span>
        </div>
      ) : (
        <>
          <div className="eyebrow">Needs your approval</div>
          <div className="ask">
            <div style={{ fontWeight: 500 }}>{summary}</div>
            {diff && <div className="diff">{diff}</div>}
            <div className="hint">Nothing is added to your records until you say yes.</div>
          </div>
          <div className="row" style={{ gap: 8, paddingBottom: 2 }}>
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
