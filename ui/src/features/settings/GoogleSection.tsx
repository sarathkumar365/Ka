import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys } from '../../lib/api'

const when = (at?: string) => (at ? new Date(at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Not yet')

/** "Connected accounts" in the design: one row per account or job, status under the name, action on the right. */
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
  const login = () => window.location.assign('/api/google/login')
  const drive = data.drive_sync
  const sheet = data.sheet
  // only a lost sign-in needs Reconnect; offline or a missing Sheet keep the sign-in (flows/google.md)
  const failed = [drive?.error, sheet?.error].some((e) => e && /reconnect/i.test(e))
  return (
    <section>
      <h2>Connected accounts</h2>
      <div className="srow">
        <div className="stext">
          <span>Google</span>
          <span>{data.connected ? (data.email ?? 'Connected') : 'Not connected'}</span>
        </div>
        {!data.connected ? (
          <button className="secondary slim" onClick={login}>
            Connect
          </button>
        ) : failed ? (
          <button className="primary slim" onClick={login}>
            Reconnect
          </button>
        ) : (
          <button className="secondary slim" disabled={run.isPending} onClick={() => run.mutate('disconnect')}>
            Disconnect
          </button>
        )}
      </div>
      {data.connected && (
        <>
          <div className="srow">
            <div className="stext">
              <span>Drive statements</span>
              <span>{drive?.error ? `Failed: ${drive.error}` : `Checked ${when(drive?.at)}`}</span>
              {(drive?.skipped ?? []).map((s) => (
                <span key={s}>Skipped: {s}</span>
              ))}
            </div>
            <button className="secondary slim" disabled={run.isPending} onClick={() => run.mutate('sync')}>
              Sync now
            </button>
          </div>
          <div className="srow">
            <div className="stext">
              <span>Sheet copy</span>
              <span>{sheet?.error ? `Failed: ${sheet.error}` : `Copied ${when(sheet?.at)}`}</span>
            </div>
            <button className="secondary slim" disabled={run.isPending} onClick={() => run.mutate('push')}>
              Copy now
            </button>
          </div>
        </>
      )}
      {msg && (
        <div className="notice" role="status">
          {msg}
        </div>
      )}
    </section>
  )
}
