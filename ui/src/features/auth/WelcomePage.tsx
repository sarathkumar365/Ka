import { Link } from 'react-router-dom'
import { Entity } from '../chat/Entity'

/** The front door: the same Ka entity as an empty chat, and the two ways in. */
export function WelcomePage() {
  return (
    <div className="app">
      <header className="bar">
        <div className="row">
          <span className="textbtn wordmark">Ka</span>
        </div>
      </header>
      <main className="screen">
        <div className="welcome col">
          <Entity mode="empty" lights={0} />
          <div className="welcome-copy">
            <h1>Ka</h1>
            <p className="lead">Your data and one agent that knows you.</p>
          </div>
          <div className="welcome-actions">
            <Link className="primary btnlink" to="/signup">
              Create account
            </Link>
            <Link className="secondary btnlink" to="/login">
              Sign in
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
