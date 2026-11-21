import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keys } from '../../lib/api'
import { type Draft, emptyDraft, hasInput } from './draft'
import { StepBasics } from './StepBasics'
import { StepDocuments } from './StepDocuments'
import { StepMemory } from './StepMemory'
import { type SendPhase, StepSend } from './StepSend'
import { StepSources } from './StepSources'
import { Progress } from '../auth/AuthFrame'

// account creation is step 1 (SetupStep); these follow it
const LABELS = ['Basics', 'Documents', 'Sources', 'Memory', 'Send']

export function OnboardingPage() {
  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [phase, setPhase] = useState<SendPhase>('idle')
  const nav = useNavigate()
  const qc = useQueryClient()
  const unsent = hasInput(draft) && (phase === 'idle' || phase === 'failed')
  useEffect(() => {
    if (!unsent) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault() // nothing is kept: say so before leaving
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsent])
  const leave = (to: string, state?: object) => {
    // the status is read from the data, so ask again: after a send it says "pending"
    qc.invalidateQueries({ queryKey: keys.onboarding })
    nav(to, { state })
  }
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
        <Progress current={step + 1} />
      )}
      {/* steps share one grid cell and slide 40px left or right, as in the design */}
      <div className="obstack">
        {[
          <StepBasics key="b" value={draft.basics} onChange={(basics) => setDraft({ ...draft, basics })} />,
          <StepDocuments key="d" files={draft.files} onChange={(files) => setDraft({ ...draft, files })} />,
          <StepSources key="s" />,
          <StepMemory key="m" entries={draft.memory} onChange={(memory) => setDraft({ ...draft, memory })} />,
        ].map((el, i) => (
          <div key={i} className="obstep" data-pos={i === step ? 'current' : i < step ? 'before' : 'after'} inert={i !== step}>
            {el}
          </div>
        ))}
        {last && (
          <div className="obstep" data-pos="current">
            <StepSend draft={draft} onPhase={onPhase} onReview={() => leave('/pending', { from: 'onboarding' })} />
          </div>
        )}
      </div>
      {!busy && (
        <div className="row" style={{ gap: 8 }}>
          <button className="secondary back" disabled={step === 0} onClick={() => setStep(step - 1)}>
            Back
          </button>
          {!last && (
            <button className="next" onClick={() => setStep(step + 1)}>
              Continue
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
