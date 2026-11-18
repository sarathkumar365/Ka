import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, keys } from '../../lib/api'
import { type EntityMode, entityStyle } from './entityStyle'
import { ThinkingRing } from './ThinkingRing'

const BEAT_MS = 2400 // the design's breathing cycle
const SWEEP_MS = 900 // the search bar crosses the box in 900ms, then turns back
const LIGHTS = [0, 1, 2, 3, 4, 5]

/**
 * The Ka entity exactly as in the design prototype (Design/extracted/app.html): one element
 * whose position, size and corners change per phase, a faint copy that trails it, the wobbly
 * thinking ring from the design's entity board, and up to six lights for the cards waiting in Pending.
 */
export function Entity({ mode }: { mode: EntityMode }) {
  const [beat, setBeat] = useState(0)
  const [sw, setSw] = useState(false)
  const { data: pending = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => setBeat((b) => b + 1), BEAT_MS)
    return () => window.clearInterval(id)
  }, [])
  useEffect(() => {
    if (mode !== 'searching') return
    const start = window.setTimeout(() => setSw(true), 60)
    const id = window.setInterval(() => setSw((s) => !s), SWEEP_MS)
    return () => {
      window.clearTimeout(start)
      window.clearInterval(id)
      setSw(false)
    }
  }, [mode])

  const e = entityStyle(mode, beat, sw)
  const box = { left: e.l, top: e.t, width: e.w, height: e.h, borderRadius: e.r }
  const lit = mode === 'empty' || mode === 'answering' || mode === 'waiting' || mode === 'docked'
  const count = lit ? pending.length : 0
  return (
    <div className="entity-stage">
      <div className="entity-trail" aria-hidden="true" style={{ ...box, transition: e.tr2 }} />
      <div
        className="entity"
        data-mode={mode}
        role="img"
        aria-label="Ka"
        style={{
          ...box,
          borderWidth: e.bw,
          borderColor: e.bc,
          background: e.bg,
          boxShadow: e.sh,
          transform: e.tf,
          transition: e.tr,
        }}
      >
        {LIGHTS.map((i) => (
          <div key={i} className="entity-light" style={{ transform: `rotate(${28 + i * 60}deg)`, opacity: i < count ? 1 : 0 }}>
            <div />
          </div>
        ))}
      </div>
      {/* thinking uses the design's wobbly ring (owner's pick); the element above shrinks into its place and hides */}
      {mode === 'thinking' && <ThinkingRing />}
    </div>
  )
}
