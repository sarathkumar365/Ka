import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys } from '../../lib/api'

const when = (at?: string) => (at ? new Date(at).toLocaleString() : 'never')

export function GoogleSection() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: keys.google, queryFn: api.googleStatus, retry: false })
  const [msg, setMsg] = useState<string | null>(null)
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.google })
    qc.invalidateQueries({ queryKey: keys.pending })
  }
  const run = useMutation({
    mutationFn: (what: 'sync' | 'push' | 'disconnect') =>
      what === 'sync' ? api.googleSync() : what === 'push' ? api.googlePush() : api.googleDisconnect(),
    onSuccess: (r, what) => {
      if (what === 'sync' && r && 'new' in r) setMsg(`${r.new} new statement(s) in Pending`)
      else setMsg(null)
      refresh()
    },
    onError: (e: Error) => {
      setMsg(e.message)
      refresh()
    },
  })
  if (!data) return null // flag off or not configured
  const drive = data.drive_sync
  const sheet = data.sheet
  return (
    <section>
      <h2>Google</h2>
      {!data.connected ? (
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="sub">Not connected. Drive statements and the Sheet copy wait until you are.</div>
          <button className="primary" onClick={() => window.location.assign('/api/google/login')}>
            Connect
          </button>
        </div>
      ) : (
        <ul className="log">
          <li>
            <span className="t">Account</span>
            <span>{data.email ?? 'connected'}</span>
          </li>
          <li>
            <span className="t">Drive sync</span>
            <span>{drive?.error ? `failed: ${drive.error}` : when(drive?.at)}</span>
          </li>
          {(drive?.skipped ?? []).map((s) => (
            <li key={s}>
              <span className="t">Skipped</span>
              <span className="sub">{s}</span>
            </li>
          ))}
          <li>
            <span className="t">Sheet copy</span>
            <span>{sheet?.error ? `failed: ${sheet.error}` : when(sheet?.at)}</span>
          </li>
        </ul>
      )}
      {msg && (
        <div className="notice" role="status">
          {msg}
        </div>
      )}
      {data.connected && (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button className="primary" disabled={run.isPending} onClick={() => run.mutate('sync')}>
            Sync now
          </button>
          <button className="secondary" disabled={run.isPending} onClick={() => run.mutate('push')}>
            Copy to Sheet
          </button>
          <button className="secondary" disabled={run.isPending} onClick={() => run.mutate('disconnect')}>
            Disconnect
          </button>
        </div>
      )}
    </section>
  )
}
