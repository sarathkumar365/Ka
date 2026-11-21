import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api, keys } from '../../lib/api'

/** Home, sign-up and sign-in are for people not signed in; anyone signed in goes to chat. */
export function SignedOut({ children }: { children: ReactNode }) {
  const { data: auth, isError } = useQuery({ queryKey: keys.auth, queryFn: api.authStatus, retry: false })
  if (isError) return children // server unreachable: signed out is the safe guess; the form says why on send
  if (!auth) return null
  return auth.user ? <Navigate to="/chat" replace /> : children
}
