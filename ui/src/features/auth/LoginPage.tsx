import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { AuthFrame } from './AuthFrame'
import { takeReturn } from './session'

/** Login form; after signing in the owner goes back to where the session ended. With no account
 * yet there is nothing to sign in to, so it hands over to the Shell, which shows account setup. */
export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: auth } = useQuery({ queryKey: keys.auth, queryFn: api.authStatus, retry: false })
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.login(username.trim().toLowerCase(), password)
      await qc.invalidateQueries()
      nav(takeReturn()?.path ?? '/chat', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in')
    } finally {
      setBusy(false)
    }
  }
  if (auth?.setup_needed) return <Navigate to="/chat" replace />
  return (
    <AuthFrame
      label="Sign in"
      title="Welcome back"
      lead="Sign in to pick up where you left off."
      error={error}
      busy={busy}
      submit="Sign in"
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
          onChange={(e) => {
            setUsername(e.target.value)
            setError(null)
          }}
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input type="password" autoComplete="current-password" value={password} onChange={(e) => {
            setPassword(e.target.value)
            setError(null)
          }} />
      </label>
    </AuthFrame>
  )
}
