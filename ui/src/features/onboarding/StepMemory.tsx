import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, keys } from '../../lib/api'
import { JobStatus } from './JobStatus'
import { ASSISTANTS, MAX_SOURCES, type MemoryEntry, nextAssistant, toItems } from './memory'
import { useIntakeJob } from './useIntakeJob'

const PROMPT =
  'List everything you have remembered about me: facts about my life and work, my preferences, and any rules I asked you to follow. One item per line. Do not guess; include only what you actually know.'

export function StepMemory() {
  const qc = useQueryClient()
  const [entries, setEntries] = useState<MemoryEntry[]>([{ id: 1, source: 'Claude', text: '' }])
  const [jobId, setJobId] = useState<string | null>(null)
  const { data: settings } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const { data: job } = useIntakeJob(jobId)
  const items = toItems(entries)
  const send = useMutation({
    mutationFn: () => api.pasteMemory(items),
    onSuccess: (r) => setJobId(r.job_id),
  })
  const running = !!job && (job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (job?.status === 'done') qc.invalidateQueries({ queryKey: keys.pending })
  }, [job?.status, qc])
  const update = (id: number, patch: Partial<MemoryEntry>) =>
    setEntries((es) => es.map((e) => (e.id === id ? { ...e, ...patch } : e)))
  const add = () =>
    setEntries((es) => [...es, { id: Math.max(...es.map((e) => e.id)) + 1, source: nextAssistant(es), text: '' }])
  const remove = (id: number) => setEntries((es) => es.filter((e) => e.id !== id))
  return (
    <div className="step">
      <h1>Bring memory from other assistants</h1>
      <p className="lead">
        Ask each assistant you use to export what it remembers about you, then paste each answer in its own box.
      </p>
      <div className="sub">
        Ask it: <em>{PROMPT}</em>{' '}
        <button className="linkbtn" onClick={() => navigator.clipboard?.writeText(PROMPT)}>
          Copy the question
        </button>
      </div>
      {entries.map((e) => (
        <div key={e.id} className="col" style={{ gap: 8 }}>
          <div className="row" style={{ gap: 8, alignItems: 'end' }}>
            <label className="field" style={{ flex: 1 }}>
              <span>Assistant</span>
              <select value={e.source} onChange={(ev) => update(e.id, { source: ev.target.value })}>
                {ASSISTANTS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            {entries.length > 1 && (
              <button className="linkbtn" disabled={running} onClick={() => remove(e.id)}>
                Remove
              </button>
            )}
          </div>
          <label className="field">
            <span>Pasted memory export from {e.source}</span>
            <textarea
              rows={6}
              value={e.text}
              maxLength={60000}
              onChange={(ev) => update(e.id, { text: ev.target.value })}
            />
          </label>
        </div>
      ))}
      {entries.length < MAX_SOURCES && (
        <div>
          <button className="linkbtn" disabled={running} onClick={add}>
            Add another assistant
          </button>
        </div>
      )}
      <div className="sub">
        Ka sends these texts to {settings?.models.default?.provider ?? 'your model provider'}. Items arrive in Pending
        marked unverified, tagged with the assistant they came from. The same fact from two assistants is kept once.
      </div>
      {send.isError && (
        <div className="notice" role="alert">
          {(send.error as Error).message}
        </div>
      )}
      <JobStatus job={job} />
      <div>
        <button
          className="secondary"
          disabled={!items.length || send.isPending || running}
          onClick={() => send.mutate()}
        >
          {running ? 'Reading…' : items.length > 1 ? `Read all ${items.length}` : 'Read this'}
        </button>
      </div>
    </div>
  )
}
