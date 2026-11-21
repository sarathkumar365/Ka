import { type FormEvent, useState } from 'react'
import type { LoopTask } from '../../lib/api'
import { canGoDirect, describeTrigger, nextRunLabel, type TriggerForm, triggerFromForm } from './loops'
import { RunList } from './RunList'
import { useLoops } from './useLoops'

function Task({ t, now }: { t: LoopTask; now: Date }) {
  const { update, remove, run, runningId } = useLoops()
  const [open, setOpen] = useState(false)
  const running = runningId === t.id
  const busy = update.isPending || remove.isPending || run.isPending || running
  return (
    <div className="card loop">
      <div className="kind">
        {t.kind === 'builtin' ? 'Built in' : t.created_by === 'ka' ? 'Made by Ka' : 'Made by you'} · {t.mode}
      </div>
      <div className="ptext">{t.name}</div>
      <div className="src">
        {describeTrigger(t.trigger)} · next: {nextRunLabel(t, now)} · last: {t.last_run ? `${t.last_run.status}` : 'never'}
      </div>
      {t.brief && t.kind === 'agent' && <div className="hint">{t.brief}</div>}
      <div className="hint">
        {t.approved} approved, {t.rejected} rejected
        {canGoDirect(t) && ' · right every time so far: it could write directly'}
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <button className="secondary" disabled={busy} onClick={() => run.mutate(t.id)}>
          {running ? 'Running…' : 'Run now'}
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => update.mutate({ id: t.id, body: { status: t.status === 'active' ? 'paused' : 'active' } })}
        >
          {t.status === 'active' ? 'Pause' : 'Resume'}
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => {
            const next = t.mode === 'shadow' ? 'direct' : 'shadow'
            if (next === 'direct' && !window.confirm('Let this task write without asking first?')) return
            update.mutate({ id: t.id, body: { mode: next } })
          }}
        >
          {t.mode === 'shadow' ? 'Allow direct writes' : 'Back to shadow mode'}
        </button>
        {t.kind !== 'builtin' && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => window.confirm(`Delete "${t.name}"?`) && remove.mutate(t.id)}
          >
            Delete
          </button>
        )}
        <button className="secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
          Runs
        </button>
      </div>
      {open && <RunList taskId={t.id} />}
      {(update.error || run.error || remove.error) && (
        <div className="notice" role="alert">
          {(update.error ?? run.error ?? remove.error)?.message}
        </div>
      )}
    </div>
  )
}

function NewTaskForm() {
  const { create } = useLoops()
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [finance, setFinance] = useState(false)
  const [when, setWhen] = useState<TriggerForm>({ every: 'weekly', hours: 6, time: '08:00', day: 'mon' })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(
      { name: name.trim(), brief: brief.trim(), trigger: triggerFromForm(when), toolkits: finance ? ['finance'] : [] },
      { onSuccess: () => (setName(''), setBrief('')) },
    )
  }
  return (
    <form className="card" onSubmit={submit} aria-label="New scheduled task">
      <div className="kind">New scheduled task (starts in shadow mode)</div>
      <label>
        <span>Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        <span>What to do</span>
        <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} />
      </label>
      <label>
        <span>When</span>
        <select value={when.every} onChange={(e) => setWhen({ ...when, every: e.target.value as TriggerForm['every'] })}>
          <option value="hours">Every few hours</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
        </select>
      </label>
      {when.every === 'hours' ? (
        <label>
          <span>Every how many hours</span>
          <input type="number" min={1} value={when.hours} onChange={(e) => setWhen({ ...when, hours: Number(e.target.value) })} />
        </label>
      ) : (
        <label>
          <span>At</span>
          <input type="time" value={when.time} onChange={(e) => setWhen({ ...when, time: e.target.value })} />
        </label>
      )}
      {when.every === 'weekly' && (
        <label>
          <span>Day</span>
          <select value={when.day} onChange={(e) => setWhen({ ...when, day: e.target.value })}>
            {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <input type="checkbox" checked={finance} onChange={(e) => setFinance(e.target.checked)} /> <span>May use finance</span>
      </label>
      {create.error && (
        <div className="notice" role="alert">
          {create.error.message}
        </div>
      )}
      <button className="primary" type="submit" disabled={create.isPending || !name.trim() || brief.trim().length < 5}>
        Save task
      </button>
    </form>
  )
}

export function LoopsPage() {
  const { list } = useLoops()
  const [now] = useState(() => new Date())
  return (
    <div className="col page loops">
      <div className="pagehead">
        <h1>Loops</h1>
        <div className="pagesub">Tasks Ka runs on its own. Their changes wait in Pending until you trust them.</div>
      </div>
      {(list.data ?? []).map((t) => (
        <Task key={t.id} t={t} now={now} />
      ))}
      <NewTaskForm />
    </div>
  )
}
