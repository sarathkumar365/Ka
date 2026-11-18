export function StepSources() {
  return (
    <div className="step">
      <h1>Connect your sources</h1>
      <p className="lead">Ka reads from these. It never changes anything in them.</p>
      <div>
        {['Bank accounts', 'Email', 'Calendar'].map((n) => (
          <div className="srcrow" key={n}>
            <span>{n}</span>
            <span className="sub" style={{ margin: 0 }}>
              Not available yet
            </span>
            <button className="secondary slim" disabled>
              Connect
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
