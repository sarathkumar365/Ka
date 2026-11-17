import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StepBasics } from './StepBasics'
import { StepDocuments } from './StepDocuments'
import { StepMemory } from './StepMemory'
import { StepReview } from './StepReview'
import { StepSources } from './StepSources'

const LABELS = ['Basics', 'Documents', 'Sources', 'Memory', 'Review']

export function OnboardingPage() {
  const [step, setStep] = useState(0)
  const nav = useNavigate()
  const last = step === LABELS.length - 1
  return (
    <div className="col page onboarding">
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
      {/* all steps stay mounted so an upload in progress survives Back and Next */}
      <div hidden={step !== 0}><StepBasics /></div>
      <div hidden={step !== 1}><StepDocuments /></div>
      <div hidden={step !== 2}><StepSources /></div>
      <div hidden={step !== 3}><StepMemory /></div>
      <div hidden={step !== 4}><StepReview /></div>
      <div className="row" style={{ gap: 8, marginTop: 24 }}>
        {step > 0 && (
          <button className="secondary" onClick={() => setStep(step - 1)}>
            Back
          </button>
        )}
        <button className="next" onClick={() => (last ? nav('/pending') : setStep(step + 1))}>
          {last ? 'Done' : 'Next'}
        </button>
      </div>
    </div>
  )
}
