import { useQuery } from '@tanstack/react-query'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api, keys, type ConversationRow } from '../lib/api'
import { Icon } from '../lib/icons'

const WEEK = 7 * 24 * 3600 * 1000

function groupConversations(rows: ConversationRow[], now: Date) {
  const recent = rows.filter((r) => now.getTime() - new Date(r.last_at).getTime() < WEEK)
  const older = rows.filter((r) => !recent.includes(r))
  return [
    { label: 'This week', rows: recent },
    { label: 'Earlier', rows: older },
  ].filter((g) => g.rows.length)
}

export function Drawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const { id } = useParams()
  const { data = [] } = useQuery({ queryKey: keys.conversations, queryFn: api.conversations })
  return (
    <>
      <button className="scrim" data-open={open} aria-label="Close chat history" onClick={onClose} />
      <aside className="drawer" data-open={open} aria-label="Chat history" aria-hidden={!open}>
        <div className="row" style={{ justifyContent: 'space-between', paddingLeft: 8 }}>
          <span style={{ fontWeight: 500 }}>Chats</span>
          <button className="iconbtn" aria-label="Close chat history" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <button className="outline-btn" onClick={() => nav('/chat')}>
          <Icon name="plus" />
          <span>New chat</span>
        </button>
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {groupConversations(data, new Date()).map((g) => (
            <div key={g.label}>
              <div className="group">{g.label}</div>
              {g.rows.map((c) => (
                <Link key={c.id} to={`/chat/${c.id}`} className="item" aria-current={c.id === id ? 'page' : undefined}>
                  {c.title}
                </Link>
              ))}
            </div>
          ))}
        </div>
        <NavLink to="/activity" className="item">
          Activity log
        </NavLink>
      </aside>
    </>
  )
}
