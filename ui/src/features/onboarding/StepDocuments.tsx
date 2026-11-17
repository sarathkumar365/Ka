import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, keys } from '../../lib/api'
import { JobStatus } from './JobStatus'
import { useIntakeJob } from './useIntakeJob'

const ACCEPT = '.pdf,.docx,.odt,.rtf,.html,.htm,.txt,.md'

export function StepDocuments() {
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const { data: settings } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const { data: job } = useIntakeJob(jobId)
  const provider = settings?.models.default?.provider ?? 'your model provider'
  const upload = useMutation({ mutationFn: () => api.uploadDocuments(files), onSuccess: (r) => setJobId(r.job_id) })
  const running = !!job && (job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (job?.status === 'done') qc.invalidateQueries({ queryKey: keys.pending })
  }, [job?.status, qc])
  const pick = (list: FileList | null) => list && setFiles(Array.from(list).slice(0, 5))
  return (
    <div className="step">
      <h1>Add your documents</h1>
      <p className="lead">
        A resume or anything that describes your work. Bank statements go through the statement import, not here.
      </p>
      <button
        className="dropzone"
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          pick(e.dataTransfer.files)
        }}
      >
        Drop files here, or choose them
      </button>
      <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => pick(e.target.files)} />
      {files.length === 0 ? (
        <div className="sub">No files yet. You can skip this and add them later.</div>
      ) : (
        <ul className="lines">
          {files.map((f, i) => (
            <li key={`${i}-${f.name}`}>{f.name}</li>
          ))}
        </ul>
      )}
      <div className="sub">
        Ka sends the text of these files to {provider} to read them. Nothing is saved until you approve it.
      </div>
      {upload.isError && (
        <div className="notice" role="alert">
          {(upload.error as Error).message}
        </div>
      )}
      <JobStatus job={job} />
      <div>
        <button className="secondary" disabled={files.length === 0 || upload.isPending || running} onClick={() => upload.mutate()}>
          {running ? 'Reading…' : 'Read these files'}
        </button>
      </div>
    </div>
  )
}
