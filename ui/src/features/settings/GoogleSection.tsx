import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useState } from 'react'
import { api, keys } from '../../lib/api'

const when = (at?: string) => (at ? new Date(at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Not yet')

/** "Connected accounts" in the design: one row per account or job, status under the name, action on the right. */
export function GoogleSection() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: keys.google, queryFn: api.googleStatus, retry: false })
  const { data: settings } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const [msg, setMsg] = useState<string | null>(null)
  const [folder, setFolder] = useState('')
  const [sheetId, setSheetId] = useState('')
  const saved = settings?.google
  useEffect(() => {
    setFolder(saved?.drive_folder_id ?? '')
    setSheetId(saved?.sheet_id ?? '')
  }, [saved?.drive_folder_id, saved?.sheet_id])
  const save = useMutation({
    mutationFn: () => api.googleSave({ drive_folder_id: folder.trim() || null, sheet_id: sheetId.trim() || null }),
    onSuccess: () => {
      setMsg('Saved')
      qc.invalidateQueries({ queryKey: keys.settings })
    },
    onError: (e: Error) => setMsg(e.message),
  })
  const changed = folder.trim() !== (saved?.drive_folder_id ?? '') || sheetId.trim() !== (saved?.sheet_id ?? '')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }
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
          {/* each account's own folder and Sheet: never shared, never taken from config.yaml */}
          <form className="gids" onSubmit={submit}>
            <label className="field">
              <span>Statements folder ID (from the Drive folder's address)</span>
              <input value={folder} onChange={(e) => setFolder(e.target.value)} autoCapitalize="none" autoCorrect="off" spellCheck={false} />
            </label>
            <label className="field">
              <span>Sheet ID (from the Sheet's address)</span>
              <input value={sheetId} onChange={(e) => setSheetId(e.target.value)} autoCapitalize="none" autoCorrect="off" spellCheck={false} />
            </label>
            <button className="secondary slim" type="submit" disabled={!changed || save.isPending}>
              Save
            </button>
          </form>
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
