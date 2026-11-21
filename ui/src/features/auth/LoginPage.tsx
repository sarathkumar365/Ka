import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { AuthFrame } from './AuthFrame'
import { takeReturn } from './session'

/** Login form; afterwards the person goes back to where their session ended (their own only). */
export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const qc = useQueryClient()
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const name = username.trim().toLowerCase()
      await api.login(name, password)
      qc.clear() // nothing cached from another account may show
      nav(takeReturn(name)?.path ?? '/chat', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in')
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthFrame
      label="Sign in"
      title="Welcome back"
      lead="Sign in to pick up where you left off."
      error={error}
      busy={busy}
      submit="Sign in"
      onSubmit={submit}
      switchTo={{ prompt: 'New here?', label: 'Create an account', to: '/signup' }}
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
