import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, keys } from '../../lib/api'

/** First step of onboarding when Ka has no account yet: create the one account. */
export function SetupStep() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const mismatch = again !== '' && again !== password
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (mismatch) return
    setBusy(true)
    setError(null)
    try {
      await api.setup(username.trim(), password)
      await qc.invalidateQueries({ queryKey: keys.auth })
      await qc.invalidateQueries()
      nav('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="col page setup" onSubmit={submit} aria-label="Create your account">
      <h1>Create your account</h1>
      <p>One account for all your devices. Your existing data moves into it.</p>
      <label>
        <span>Username</span>
        <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} />
      </label>
      <label>
        <span>Password (10 characters or more)</span>
        <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      <label>
        <span>Password again</span>
        <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
      </label>
      {mismatch && <p role="alert">The passwords differ.</p>}
      {error && <p role="alert">{error}</p>}
      <button
        className="outline-btn"
        type="submit"
        disabled={busy || !username || password.length < 10 || again !== password}
      >
        Create account
      </button>
    </form>
  )
}
