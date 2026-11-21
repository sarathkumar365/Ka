import { useQuery } from '@tanstack/react-query'
import { type MouseEvent, useEffect, useRef, useState } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { SetupStep } from '../features/auth/SetupStep'
import { api, keys } from '../lib/api'
import { useFirstRunRedirect } from '../features/onboarding/gate'
import { Icon } from '../lib/icons'
import { Drawer } from './Sidebar'
import { KaRingLayer } from '../features/onboarding/KaRing'

export function Shell() {
  // No focus refetch: an expired session is found by the next API call's 401, which saves the
  // place and the unsent message before going to login (see auth/session.ts).
  const { data: auth, isLoading } = useQuery({
    queryKey: keys.auth,
    queryFn: api.authStatus,
    retry: false,
    refetchOnWindowFocus: false,
  })
  if (isLoading || !auth) return null
  if (!auth.user) return auth.setup_needed ? <SetupStep rules={auth} /> : <Navigate to="/login" replace />
  return <SignedIn />
}

function SignedIn() {
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { data: pending = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  useEffect(() => setOpen(false), [pathname])
  const { data: onboarding } = useQuery({
    queryKey: keys.onboarding,
    queryFn: api.onboardingStatus,
    retry: false,
    refetchOnWindowFocus: false,
  })
  useFirstRunRedirect(onboarding, pathname, nav)
  const count = pending.length
  // Pressing the icon of the screen you are on takes you back to chat, as in the design.
  const lastChat = useRef('/chat')
  useEffect(() => {
    if (pathname.startsWith('/chat')) lastChat.current = pathname
  }, [pathname])
  const backToChat = (path: string) => (e: MouseEvent) => {
    if (!pathname.startsWith(path) || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    e.preventDefault()
    nav(lastChat.current)
  }
  return (
    <KaRingLayer>
    <div className="app">
      <header className="bar">
        <div className="row">
          <button className="iconbtn" aria-label="Chat history" onClick={() => setOpen(true)}>
            <Icon name="history" />
          </button>
          <button className="textbtn" onClick={() => nav('/chat')}>
            Ka
          </button>
        </div>
        <div className="row">
          <NavLink
            to="/pending"
            className="iconbtn"
            data-pending-bell
            aria-label={`Pending, ${count} waiting`}
            onClick={backToChat('/pending')}
          >
            <Icon name="inbox" />
            {/* always rendered so it can scale in and out (design) */}
            <span className="badge" data-on={count > 0}>
              {count || ''}
            </span>
          </NavLink>
          <NavLink to="/settings" className="iconbtn" aria-label="Settings" onClick={backToChat('/settings')}>
            <Icon name="sliders" />
          </NavLink>
        </div>
      </header>
      <main className="screen">
        <Outlet />
      </main>
      <Drawer open={open} onClose={() => setOpen(false)} />
    </div>
    </KaRingLayer>
  )
}
