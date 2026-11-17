import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, keys } from '../lib/api'
import { Icon } from '../lib/icons'
import { Drawer } from './Sidebar'

export function Shell() {
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { data: pending = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  useEffect(() => setOpen(false), [pathname])
  const count = pending.length
  return (
    <div className="app">
      <header className="bar">
        <div className="row">
          <button className="iconbtn" aria-label="Chat history" onClick={() => setOpen(true)}>
            <Icon name="menu" />
          </button>
          <button className="textbtn" onClick={() => nav('/chat')}>
            Ka
          </button>
        </div>
        <div className="row">
          <NavLink to="/pending" className="iconbtn" aria-label={count ? `Pending, ${count} waiting` : 'Pending'}>
            <Icon name="bell" />
            {count > 0 && <span className="badge">{count}</span>}
          </NavLink>
          <NavLink to="/settings" className="iconbtn" aria-label="Settings">
            <Icon name="gear" />
          </NavLink>
        </div>
      </header>
      <main className="screen">
        <Outlet />
      </main>
      <Drawer open={open} onClose={() => setOpen(false)} />
    </div>
  )
}
