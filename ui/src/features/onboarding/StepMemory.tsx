import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, keys } from '../../lib/api'
import { JobStatus } from './JobStatus'
import { useIntakeJob } from './useIntakeJob'

const PROMPT =
  'List everything you have remembered about me: facts about my life and work, my preferences, and any rules I asked you to follow. One item per line. Do not guess; include only what you actually know.'

export function StepMemory() {
  const qc = useQueryClient()
  const [source, setSource] = useState('Claude')
  const [text, setText] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const { data: settings } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const { data: job } = useIntakeJob(jobId)
  const send = useMutation({
    mutationFn: () => api.pasteMemory({ text, source: source.toLowerCase() }),
    onSuccess: (r) => setJobId(r.job_id),
  })
  const running = !!job && (job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (job?.status === 'done') qc.invalidateQueries({ queryKey: keys.pending })
  }, [job?.status, qc])
  return (
    <div className="step">
      <h1>Bring memory from other assistants</h1>
      <p className="lead">Ask another assistant to export what it remembers about you, then paste it here.</p>
      <label className="field">
        <span>Assistant</span>
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          {['Claude', 'ChatGPT', 'Gemini'].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <div className="sub">
        Ask it: <em>{PROMPT}</em>{' '}
        <button className="linkbtn" onClick={() => navigator.clipboard?.writeText(PROMPT)}>
          Copy the question
        </button>
      </div>
      <label className="field">
        <span>Pasted memory export</span>
        <textarea rows={7} value={text} maxLength={60000} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="sub">
        Ka sends this text to {settings?.models.default?.provider ?? 'your model provider'}. Items arrive in Pending marked unverified.
      </div>
      {send.isError && (
        <div className="notice" role="alert">
          {(send.error as Error).message}
        </div>
      )}
      <JobStatus job={job} />
      <div>
        <button className="secondary" disabled={!text.trim() || send.isPending || running} onClick={() => send.mutate()}>
          {running ? 'Reading…' : 'Read this'}
        </button>
      </div>
    </div>
  )
}
