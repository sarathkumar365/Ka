import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { getTheme, setTheme } from '../../lib/theme'
import { GoogleSection } from './GoogleSection'

/** Feature flags in the design's words. Only these are shown; `web_ui` is left out because you are using it. */
const FLAGS: Record<string, [string, string]> = {
  intake: ['Setup and imports', 'Read a resume or what another assistant knows into Pending.'],
  google: ['Google Drive and Sheets', 'Pick up statements from Drive and keep a Sheet copy.'],
  private_routing: ['Private model for money', 'Questions about money go to a private model.'],
  nightly_extraction: ['Suggest facts and rules', 'Ka proposes what it notices. You still approve each one.'],
  category_suggestions: ['Category suggestions', 'Ka suggests a category for new transactions.'],
}
const ROLES: Record<string, string> = { default: 'Answers' }

function Switch({ on, label, onClick }: { on: boolean; label: string; onClick?: () => void }) {
  // without onClick the switch only shows the state: flags are set in config.yaml
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      className="switch"
      aria-disabled={!onClick || undefined}
      aria-describedby={onClick ? undefined : 'flags-note'}
      title={onClick ? undefined : 'Set in config.yaml'}
      onClick={onClick}
    >
      <span />
    </button>
  )
}

function Model({ label, value }: { label: string; value: string }) {
  return (
    <label className="srow wrap">
      <span>{label}</span>
      <select className="pick" disabled title="Set in config.yaml" value={value}>
        <option>{value}</option>
      </select>
    </label>
  )
}

export function SettingsPage() {
  const { data } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const [light, setLight] = useState(getTheme() === 'light')
  const toggle = () => {
    setTheme(light ? 'dark' : 'light')
    setLight(!light)
  }
  const flags = Object.entries(data?.flags ?? {}).filter(([k]) => k in FLAGS) // known features only
  return (
    <div className="col page settings">
      <h1>Settings</h1>
      <section>
        <h2>Models</h2>
        {Object.entries(data?.models ?? {}).map(([role, m]) => (
          <Model key={role} label={ROLES[role] ?? role} value={m.model} />
        ))}
        {data?.flags.private_routing && data.private_models.length > 0 && (
          <Model label="Questions about money" value={data.private_models[0].model} />
        )}
      </section>
      {data?.flags.google && <GoogleSection />}
      <section>
        <h2>Features</h2>
        <span id="flags-note" className="vh">
          Set in config.yaml
        </span>
        {flags.map(([name, on]) => {
          const [label, desc] = FLAGS[name] ?? [name, '']
          return (
            <div key={name} className="srow">
              <div className="stext">
                <span>{label}</span>
                {desc && <span>{desc}</span>}
              </div>
              <Switch on={on} label={label} />
            </div>
          )
        })}
      </section>
      <section>
        <h2>Appearance</h2>
        <div className="srow">
          <div className="stext">
            <span>Light mode</span>
            <span>Soft dark grey is the default.</span>
          </div>
          <Switch on={light} label="Light mode" onClick={toggle} />
        </div>
      </section>
      <section>
        <h2>More</h2>
        <Link className="morerow" to="/activity">
          <span>Activity log</span>
          <Icon name="chevron" />
        </Link>
        {data?.flags.intake && (
          <Link className="morerow" to="/onboarding">
            <span>Go through setup again</span>
            <Icon name="chevron" />
          </Link>
        )}
      </section>
    </div>
  )
}
