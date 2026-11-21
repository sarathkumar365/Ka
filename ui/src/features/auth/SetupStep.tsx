import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { AuthFrame } from './AuthFrame'
import { type Rules, setupProblem } from './rules'

/** Step 1 of onboarding when Ka has no account yet: create the one account. */
export function SetupStep({ rules }: { rules: Rules }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const edit = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    set(e.target.value)
    setError(null)
  }
  const mismatch = again !== '' && !password.startsWith(again)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const problem = setupProblem(rules, username, password, again)
    setError(problem)
    if (problem) return
    setBusy(true)
    try {
      await api.setup(username.trim(), password)
      await qc.invalidateQueries()
      nav('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthFrame
      label="Create your account"
      title="Welcome to Ka"
      lead="First, an account. It keeps your data private and lets you sign in from your phone too."
      step={0}
      error={error}
      busy={busy}
      submit="Create account"
      onSubmit={submit}
    >
      <label className="field">
        <span>Username</span>
        <input
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={username}
          onChange={edit((v) => setUsername(v.toLowerCase()))}
        />
        <small className="hint">Letters, numbers, - or _, starting with a letter</small>
      </label>
      <label className="field">
        <span>Password</span>
        <input type="password" autoComplete="new-password" value={password} onChange={edit(setPassword)} />
        <small className="hint" data-ok={password.length >= rules.min_password}>
          {rules.min_password} characters or more
        </small>
      </label>
      <label className="field">
        <span>Password again</span>
        <input type="password" autoComplete="new-password" value={again} onChange={edit(setAgain)} />
        {mismatch && <small className="hint">Does not match yet</small>}
      </label>
    </AuthFrame>
  )
}
