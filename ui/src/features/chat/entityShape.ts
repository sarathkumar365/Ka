/**
 * Geometry of the Ka entity, ported from the design (Design/Ka.html, "Ka entity" board).
 * The shape is a rounded rectangle walked by perimeter fraction s in [0, 1); every point is
 * pushed along its normal by three sine lobes moving at different speeds, so a circle wobbles
 * and the same code draws the small ring, the search bar and the big blob.
 */
import type { Phase } from './state'

export type EntityMode = 'empty' | 'thinking' | 'searching' | 'answering' | 'waiting' | 'docked'

export function entityMode(phase: Phase, hasItems: boolean): EntityMode {
  if (phase === 'idle') return hasItems ? 'docked' : 'empty'
  return phase
}

export type Geo = { x: number; y: number; hw: number; hh: number; r: number }
export type Spring = { x: number; v: number }

const fmt = (n: number) => Math.round(n * 10) / 10

function fix(g: Geo): Geo {
  const hw = Math.max(1, g.hw)
  const hh = Math.max(1, g.hh)
  return { x: g.x, y: g.y, hw, hh, r: Math.max(0.5, Math.min(g.r, hw, hh)) }
}

/** Point and outward normal at perimeter fraction s, starting top-left and going clockwise. */
export function pt(g: Geo, s: number): [number, number, number, number] {
  const r = g.r
  const w = g.hw - r
  const h = g.hh - r
  const a = 2 * w
  const b = 2 * h
  const q = (Math.PI * r) / 2
  let d = (((s % 1) + 1) % 1) * (2 * a + 2 * b + 4 * q)
  const arc = (cx: number, cy: number, a0: number): [number, number, number, number] => {
    const an = a0 + d / r
    return [cx + r * Math.cos(an), cy + r * Math.sin(an), Math.cos(an), Math.sin(an)]
  }
  if (d < a) return [g.x - w + d, g.y - g.hh, 0, -1]
  d -= a
  if (d < q) return arc(g.x + w, g.y - h, -Math.PI / 2)
  d -= q
  if (d < b) return [g.x + g.hw, g.y - h + d, 1, 0]
  d -= b
  if (d < q) return arc(g.x + w, g.y + h, 0)
  d -= q
  if (d < a) return [g.x + w - d, g.y + g.hh, 0, 1]
  d -= a
  if (d < q) return arc(g.x - w, g.y + h, Math.PI / 2)
  d -= q
  if (d < b) return [g.x - g.hw, g.y + h - d, -1, 0]
  d -= b
  return arc(g.x - w, g.y - h, Math.PI)
}

/** Outward push at s: lobes 2, 3 and 5 drift at different speeds, so the outline never repeats. */
export function disp(s: number, t: number, scale: number, phase: number): number {
  const a = s * 2 * Math.PI
  return (
    scale *
    (Math.sin(a * 2 + t * 0.9 + phase) * 0.6 +
      Math.sin(a * 3 - t * 0.6 + 1.7 + phase) * 0.4 +
      Math.sin(a * 5 + t * 1.3) * 0.18)
  )
}

/** Closed SVG path of the wobbling outline; `amp` is the wobble as a fraction of the short half-side. */
export function shapePath(g0: Geo, amp: number, t: number, phase = 0): string {
  const g = fix(g0)
  const N = 160
  const scale = Math.min(g.hw, g.hh) * amp
  const pts: [number, number][] = []
  for (let i = 0; i < N; i++) {
    const s = i / N
    const p = pt(g, s)
    const d = disp(s, t, scale, phase)
    pts.push([p[0] + p[2] * d, p[1] + p[3] * d])
  }
  const last = pts[N - 1]
  let out = `M${fmt((last[0] + pts[0][0]) / 2)} ${fmt((last[1] + pts[0][1]) / 2)}`
  for (let i = 0; i < N; i++) {
    const c = pts[i]
    const n = pts[(i + 1) % N]
    out += `Q${fmt(c[0])} ${fmt(c[1])} ${fmt((c[0] + n[0]) / 2)} ${fmt((c[1] + n[1]) / 2)}`
  }
  return out + 'Z'
}

/** The thinking arc: 28% of the outline, travelling at 0.45 turns per second. */
export function arcPath(g0: Geo, t: number): string {
  const g = fix(g0)
  const u = t * 0.45
  let out = ''
  for (let i = 0; i <= 24; i++) {
    const p = pt(g, u + (i / 24) * 0.28)
    out += `${i ? 'L' : 'M'}${fmt(p[0])} ${fmt(p[1])}`
  }
  return out
}

/** Pending lights: one dot per waiting card (up to six), riding the wobbling edge. */
export function lightsPath(g0: Geo, levels: number[], t: number, scale: number, still: boolean): string {
  const g = fix(g0)
  const mn = Math.min(g.hw, g.hh)
  const show = Math.max(0, Math.min(1, (mn - 4) / 5))
  const base = Math.max(1.8, Math.min(4, mn * 0.07)) * show
  let out = ''
  levels.forEach((lv, i) => {
    const r = base * Math.max(0, Math.min(1.2, lv))
    if (r < 0.2) return
    const s = i / 6 + 0.08 + (still ? 0 : t * 0.008)
    const p = pt(g, s)
    const d = disp(((s % 1) + 1) % 1, t, scale, 0)
    const x = p[0] + p[2] * d
    const y = p[1] + p[3] * d
    out += `M${fmt(x - r)} ${fmt(y)}a${fmt(r)} ${fmt(r)} 0 1 0 ${fmt(2 * r)} 0a${fmt(r)} ${fmt(r)} 0 1 0 ${fmt(-2 * r)} 0Z`
  })
  return out || 'M0 0'
}

/** Damped spring, two half-steps per frame as in the design; snaps when motion is reduced. */
export function spring(s: Spring, target: number, dt: number, stiff: number, damp: number, snap: boolean): void {
  if (snap) {
    s.x = target
    s.v = 0
    return
  }
  const h = dt / 2
  for (let i = 0; i < 2; i++) {
    s.v += (stiff * (target - s.x) - damp * s.v) * h
    s.x += s.v * h
  }
}
