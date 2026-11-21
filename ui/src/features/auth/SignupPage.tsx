import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { AuthFrame } from './AuthFrame'
import { setupProblem } from './rules'

/** Step 1 of onboarding: create an account, then the onboarding page takes over. */
export function SignupPage() {
  const { data: auth } = useQuery({ queryKey: keys.auth, queryFn: api.authStatus, retry: false })
  const rules = auth ?? { min_password: 10, username_rule: '^[a-z][a-z0-9_-]{2,31}$' }
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
      await api.signup(username.trim(), password)
      qc.clear() // nothing cached from before this account may show
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
      switchTo={{ prompt: 'Already have an account?', label: 'Sign in', to: '/login' }}
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
