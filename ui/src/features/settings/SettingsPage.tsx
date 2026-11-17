import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys } from '../../lib/api'
import { Link } from 'react-router-dom'
import { getTheme, setTheme } from '../../lib/theme'

export function SettingsPage() {
  const { data } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const [light, setLight] = useState(getTheme() === 'light')
  const toggle = () => {
    setTheme(light ? 'dark' : 'light')
    setLight(!light)
  }
  return (
    <div className="col page">
      <h1>Settings</h1>
      <section>
        <h2>Models</h2>
        <ul className="log">
          {Object.entries(data?.models ?? {}).map(([role, m]) => (
            <li key={role}>
              <span className="t">{role}</span>
              <span className="mono">
                {m.provider} / {m.model}
              </span>
            </li>
          ))}
        </ul>
        <p className="sub">Change models in config.yaml.</p>
      </section>
      <section>
        <h2>Features</h2>
        <ul className="log">
          {Object.entries(data?.flags ?? {}).map(([name, on]) => (
            <li key={name}>
              <span className="t">{name}</span>
              <span>{on ? 'On' : 'Off'}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Appearance</h2>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div>
            <div>Light mode</div>
            <div className="sub">Dark is the default.</div>
          </div>
          <button role="switch" aria-checked={light} aria-label="Light mode" className="switch" onClick={toggle}>
            <span />
          </button>
        </div>
      </section>
      {data?.flags.intake && (
        <section>
          <h2>More</h2>
          <Link className="morerow" to="/onboarding">
            <span>Go through setup again</span>
          </Link>
        </section>
      )}
    </div>
  )
}
