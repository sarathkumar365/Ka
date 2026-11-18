/** Pure geometry for the onboarding ring. The canvas loop in KaRing.tsx draws with these. */
import type { PartState } from '../../lib/api'

export const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/** Per-frame settle factor for a frame of `dtMs`, so a morph takes the same time at 60 or 120 Hz. */
export function settleFactor(k60: number, dtMs: number): number {
  return 1 - (1 - k60) ** (Math.min(dtMs, 100) / (1000 / 60))
}

/** Spring-like settle (living-transitions: m += (target - m) * 0.085 at 60 Hz). */
export function approach(cur: number, target: number, k: number): number {
  const next = cur + (target - cur) * k
  return Math.abs(target - next) < 0.01 ? target : next
}

/** One arc per job part, clockwise from 12 o'clock, with `gap` radians between them. */
export function arcs(n: number, gap: number): { start: number; end: number }[] {
  if (n <= 0) return []
  const span = (2 * Math.PI) / n
  return Array.from({ length: n }, (_, i) => {
    const start = -Math.PI / 2 + i * span + gap / 2
    return { start, end: start + span - gap }
  })
}

/** Brightness of a part's arc: done is solid, the part being read pulses, failed fades back. */
export function partAlpha(state: PartState, t: number): number {
  if (state === 'done') return 1
  if (state === 'failed') return 0.12
  if (state === 'reading') return 0.55 + 0.35 * (0.5 + 0.5 * Math.sin(t * 4))
  return 0.25
}
