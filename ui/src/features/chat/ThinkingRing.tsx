import { useEffect, useRef } from 'react'
import { ringPath } from './ringPath'

/**
 * The thinking ring from the design's "Ka entity" board: a small ring that breathes (radius 9
 * ±1.5 px) and wobbles (three sine lobes drifting at different speeds), with a bright arc, 28% of
 * the outline, drifting round it at 0.45 turns a second. The owner picked it over the prototype's
 * spinning arc. Centred where the prototype's 20 px thinking ring sits.
 */
export function ThinkingRing() {
  const ring = useRef<SVGPathElement>(null)
  const arc = useRef<SVGPathElement>(null)
  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t0 = performance.now()
    let raf = 0
    const frame = (now: number) => {
      const p = ringPath((now - t0) / 1000, still)
      ring.current?.setAttribute('d', p.ring)
      arc.current?.setAttribute('d', p.arc)
      if (!still) raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])
  return (
    <svg className="thinking-ring" width="40" height="40" viewBox="-20 -20 40 40" aria-hidden="true">
      <path ref={ring} className="tr-edge" />
      <path ref={arc} className="tr-arc" />
    </svg>
  )
}
