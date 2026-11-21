import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { STEPS } from './rules'

export function Progress({ current }: { current: number }) {
  return (
    <div className="row progress" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 6 }}>
        {STEPS.map((l, i) => (
          <div key={l} className="dot" data-on={i <= current} data-current={i === current} />
        ))}
      </div>
      <div className="steplabel" aria-live="polite">
        Step {current + 1} of {STEPS.length}
        <span className="vh">: {STEPS[current]}</span>
      </div>
    </div>
  )
}

/** Screens shown before sign-in: the app's header and screen frame, with an onboarding page in it,
 * so nothing moves when the signed-in app takes over. */
export function AuthFrame(props: {
  label: string
  title: string
  lead: string
  step?: number
  error: string | null
  busy: boolean
  submit: string
  onSubmit: (e: FormEvent) => void
  /** The way to the other screen: sign-up links to sign-in and back. */
  switchTo: { prompt: string; label: string; to: string }
  children: ReactNode
}) {
  return (
    <div className="app">
      <header className="bar">
        <div className="row">
          <Link className="textbtn wordmark" to="/welcome" aria-label="Ka home">
            Ka
          </Link>
        </div>
      </header>
      <main className="screen">
        <form className="col page onboarding auth" onSubmit={props.onSubmit} aria-label={props.label} noValidate>
          {props.step !== undefined && <Progress current={props.step} />}
          <div className="step">
            <h1>{props.title}</h1>
            <p className="lead">{props.lead}</p>
            {props.children}
            {props.error && (
              <p className="formerr" role="alert">
                {props.error}
              </p>
            )}
          </div>
          <button className="primary" type="submit" disabled={props.busy} aria-busy={props.busy}>
            {props.busy ? 'One moment…' : props.submit}
          </button>
          <p className="authswitch">
            {props.switchTo.prompt} <Link to={props.switchTo.to}>{props.switchTo.label}</Link>
          </p>
        </form>
      </main>
    </div>
  )
}
