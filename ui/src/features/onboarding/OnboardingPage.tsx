import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { type Draft, emptyDraft, hasInput } from './draft'
import { StepBasics } from './StepBasics'
import { StepDocuments } from './StepDocuments'
import { StepMemory } from './StepMemory'
import { type SendPhase, StepSend } from './StepSend'
import { StepSources } from './StepSources'

const LABELS = ['Basics', 'Documents', 'Sources', 'Memory', 'Send']

export function OnboardingPage() {
  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [phase, setPhase] = useState<SendPhase>('idle')
  const nav = useNavigate()
  const qc = useQueryClient()
  const finish = useMutation({
    mutationFn: api.completeOnboarding,
    // Settled, not success: a failed save must not leave the owner stuck; the skip holds for this page load.
    onSettled: () => qc.setQueryData(keys.onboarding, { needed: false, reason: 'done' }),
  })
  const unsent = hasInput(draft) && (phase === 'idle' || phase === 'failed')
  useEffect(() => {
    if (!unsent) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault() // nothing is kept: say so before leaving
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsent])
  const leave = (to: string, state?: object) => finish.mutate(undefined, { onSettled: () => nav(to, { state }) })
  const skip = () => {
    if (unsent && !window.confirm('Leave setup? What you entered is not saved.')) return
    leave('/chat')
  }
  const onPhase = useCallback((p: SendPhase) => setPhase(p), [])
  const last = step === LABELS.length - 1
  const busy = phase === 'sending' || phase === 'running' || phase === 'done'
  return (
    <div className="col page onboarding">
      {!busy && (
        <div className="row progress" style={{ gap: 12 }}>
          <div className="row" style={{ gap: 6 }}>
            {LABELS.map((l, i) => (
              <div key={l} className="dot" data-on={i <= step} data-current={i === step} />
            ))}
          </div>
          <div className="sub" style={{ margin: 0 }}>
            Step {step + 1} of {LABELS.length}: {LABELS[step]}
          </div>
        </div>
      )}
      <div hidden={step !== 0}>
        <StepBasics value={draft.basics} onChange={(basics) => setDraft({ ...draft, basics })} />
      </div>
      <div hidden={step !== 1}>
        <StepDocuments files={draft.files} onChange={(files) => setDraft({ ...draft, files })} />
      </div>
      <div hidden={step !== 2}>
        <StepSources />
      </div>
      <div hidden={step !== 3}>
        <StepMemory entries={draft.memory} onChange={(memory) => setDraft({ ...draft, memory })} />
      </div>
      {last && <StepSend draft={draft} onPhase={onPhase} onReview={() => leave('/pending', { from: 'onboarding' })} />}
      {!busy && (
        <div className="row" style={{ gap: 8, marginTop: 24 }}>
          {step > 0 && (
            <button className="secondary" onClick={() => setStep(step - 1)}>
              Back
            </button>
          )}
          {!last && (
            <button className="next" onClick={() => setStep(step + 1)}>
              Next
            </button>
          )}
          <button className="linkbtn" style={{ marginLeft: 'auto' }} onClick={skip}>
            Skip for now
          </button>
        </div>
      )}
    </div>
  )
}
