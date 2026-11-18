import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useKaRing } from './KaRing'
import { api, keys, type PartState } from '../../lib/api'
import { basicsFilled, type Draft, hasInput, summaryLine, toForm } from './draft'
import { toItems } from './memory'
import { reducedMotion } from './ring'
import { useIntakeJob } from './useIntakeJob'

export type SendPhase = 'idle' | 'sending' | 'running' | 'done' | 'failed'

const MIN_THINKING_MS = 900 // a fast answer must not flash past the ring
const FORM_FADE_MS = 220 // matches .step.leaving transition in styles.css

/** The parts Ka will read, in the order the server reports them (see runner.run_onboarding_job). */
function draftParts(d: Draft): PartState[] {
  const basics = basicsFilled(d.basics) ? 1 : 0
  return Array(basics + d.files.length + toItems(d.memory).length).fill('waiting')
}

function useCountUp(target: number, run: boolean): number {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!run) return
    if (reducedMotion() || target === 0) {
      setN(target)
      return
    }
    const start = performance.now()
    let id = 0
    const tick = () => {
      const p = Math.min(1, (performance.now() - start) / 700)
      setN(Math.round(target * (1 - (1 - p) ** 3)))
      if (p < 1) id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [target, run])
  return n
}

export function StepSend({
  draft,
  onPhase,
  onReview,
}: {
  draft: Draft
  onPhase: (p: SendPhase) => void
  onReview: () => void
}) {
  const ring = useKaRing()
  const qc = useQueryClient()
  const buttonRef = useRef<HTMLButtonElement>(null)
  const slotRef = useRef<HTMLDivElement>(null)
  const sentAt = useRef(0)
  const landed = useRef(false)
  const flying = useRef(false) // the ring is on its way to the bell: let it finish after unmount
  const navTimer = useRef(0)
  const [leaving, setLeaving] = useState(false) // the form is fading out
  const [stageOn, setStageOn] = useState(false) // the form has gone; the stage holds the ring
  const [buttonHidden, setButtonHidden] = useState(false)
  const [settled, setSettled] = useState(false) // minimum thinking time has passed
  const [reviewing, setReviewing] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const { data: settings } = useQuery({ queryKey: keys.settings, queryFn: api.settings })
  const { data: pending = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  const { data: job } = useIntakeJob(jobId)
  const send = useMutation({ mutationFn: () => api.sendOnboarding(toForm(draft)), onSuccess: (r) => setJobId(r.job_id) })
  const phase: SendPhase = send.isPending
    ? 'sending'
    : send.isError || job?.status === 'failed'
      ? 'failed'
      : job?.status === 'done'
        ? 'done'
        : jobId
          ? 'running'
          : 'idle'
  const stage = stageOn && phase !== 'failed'
  const showDone = phase === 'done' && settled
  const parts: PartState[] = job?.result.parts?.map((p) => p.state) ?? draftParts(draft)
  const r = job?.result
  const total = useCountUp(r?.cards ?? 0, showDone) // cards queued for review, all kinds

  useEffect(() => onPhase(phase), [phase, onPhase])
  useEffect(() => {
    if (phase === 'done') qc.invalidateQueries({ queryKey: keys.pending })
  }, [phase, qc])
  useEffect(() => {
    if (phase !== 'done') return
    const wait = Math.max(0, MIN_THINKING_MS - (performance.now() - sentAt.current))
    const id = setTimeout(() => setSettled(true), wait)
    return () => clearTimeout(id)
  }, [phase])
  useEffect(() => {
    if (!leaving) return
    const id = setTimeout(() => setStageOn(true), FORM_FADE_MS)
    return () => clearTimeout(id)
  }, [leaving])
  useEffect(() => {
    if (phase !== 'failed') return
    setLeaving(false)
    setStageOn(false)
  }, [phase])

  // Drive the one ring through the phases. The layer eases every change; nothing restarts.
  const partsKey = parts.join()
  useEffect(() => {
    if (reviewing) return
    if (stage) {
      ring({ mode: showDone ? 'solid' : 'ring', rect: () => slotRef.current?.getBoundingClientRect() ?? null, parts })
    } else if (phase === 'failed' && buttonHidden) {
      // the ring morphs back into the button, which reappears when it lands
      ring({
        mode: 'pill',
        rect: () => buttonRef.current?.getBoundingClientRect() ?? null,
        onArrive: () => {
          setButtonHidden(false)
          ring({ mode: 'hidden' })
        },
      })
    }
    // parts is compared by value through partsKey, so a poll with the same states does nothing
  }, [ring, stage, showDone, phase, buttonHidden, reviewing, partsKey])
  useEffect(
    () => () => {
      clearTimeout(navTimer.current)
      if (!flying.current) ring({ mode: 'hidden' })
    },
    [ring],
  )

  const start = () => {
    const button = buttonRef.current
    sentAt.current = performance.now()
    setSettled(false)
    send.mutate()
    // the ring takes the button's exact shape first, so the hand-over is invisible
    ring({ mode: 'pill', rect: () => button?.getBoundingClientRect() ?? null })
    setButtonHidden(true)
    setLeaving(true)
  }
  const retry = () => {
    setJobId(null)
    send.reset()
    start()
  }
  const review = () => {
    if (reviewing) return
    setReviewing(true)
    if (pending.length === 0) {
      // nothing waiting, so no badge to become: the ring fades where it is
      ring({ mode: 'hidden' })
      navTimer.current = window.setTimeout(onReview, 250)
      return
    }
    landed.current = false
    flying.current = true
    ring({
      mode: 'badge',
      label: String(pending.length),
      rect: () => {
        const badge = document.querySelector('[data-pending-bell] .badge')
        if (badge) return badge.getBoundingClientRect()
        const bell = document.querySelector('[data-pending-bell]')?.getBoundingClientRect()
        return bell ? new DOMRect(bell.right - 14, bell.top - 2, 18, 18) : null
      },
      onArrive: () => {
        if (landed.current) return
        landed.current = true
        flying.current = false
        ring({ mode: 'hidden' }) // the real badge underneath takes over
      },
    })
    navTimer.current = window.setTimeout(onReview, 350) // Pending fades in behind the travelling ring
  }

  const provider = settings?.models.default?.provider ?? 'your model provider'
  const b = draft.basics
  const memory = toItems(draft.memory)

  if (stage)
    return (
      <div key="stage" className={`step sendstage${reviewing ? ' leaving' : ''}`}>
        {/* the canvas ring is drawn over this slot; its size lives in styles.css (.ringslot) */}
        <div ref={slotRef} className="ringslot">
          <span className={`ringcount${showDone ? ' in' : ''}`} aria-hidden={!showDone}>
            {total}
          </span>
        </div>
        <div className={`ringcaption${showDone ? ' out' : ''}`} aria-live="polite">
          {phase === 'done' ? 'Finishing up' : job?.step || 'Sending'}…
        </div>
        <div className={`summarygroup${showDone ? ' in' : ''}`} aria-live="polite">
          {showDone && r && (
            <>
              <p className="lead">
                {summaryLine({ cards: r.cards ?? 0, jobs: r.jobs ?? 0, highlights: r.highlights ?? 0, memories: r.memories ?? 0 })}
              </p>
              {[...(r.warnings ?? []), ...(r.skipped ?? []).map((s) => `Skipped: ${s}`)].map((w, i) => (
                <div key={`${i}-${w}`} className="sub">
                  {w}
                </div>
              ))}
              <div>
                <button className="primary" disabled={reviewing} onClick={review}>
                  Review in Pending
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    )
  return (
    <div key="form" className={`step${leaving ? ' leaving' : ''}`}>
      <h1>Send it to Ka</h1>
      <p className="lead">Ka reads everything in one go and puts what it finds in Pending. Nothing is saved until you approve it.</p>
      <ul className="lines">
        <li>Basics: {[b.name, b.where, b.role].filter((v) => v.trim()).join(', ') || 'none'}</li>
        <li>Documents: {draft.files.map((f) => f.name).join(', ') || 'none'}</li>
        <li>Memory from: {memory.map((m) => m.source).join(', ') || 'none'}</li>
      </ul>
      <div className="sub">Ka sends this to {provider} to read it.</div>
      {phase === 'failed' && (
        <div className="notice" role="alert">
          {send.isError ? (send.error as Error).message : job?.message}
        </div>
      )}
      <div>
        <button
          ref={buttonRef}
          className="primary"
          style={buttonHidden ? { visibility: 'hidden' } : undefined}
          disabled={!hasInput(draft) || send.isPending || (leaving && phase !== 'failed')}
          onClick={() => (phase === 'failed' ? retry() : start())}
        >
          {phase === 'failed' ? 'Try again' : 'Send to Ka'}
        </button>
      </div>
    </div>
  )
}
