import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api, keys } from '../../lib/api'
import { arcPath, type EntityMode, type Geo, lightsPath, shapePath, type Spring, spring } from './entityShape'


type Goal = Geo & { wob: number; a: number; br: number; arc: number; fill: number }
type Box = { left: number; top: number; width: number; height: number }

const EMPTY_R = 76 // the empty-home text sits below it at top: calc(40% + 104px) in styles.css
const DESIGN_WOB = 0.055 // the design's rest wobble (0.025 + 0.15 * (1 - 80% fresh))
const REST_WOB = 0.085 // the empty home wobbles more than the design, by request
const LIGHTS = 6

/** Rest wobble that swells and calms on a slow cycle, so the blob is not uniform over time. */
const restWob = (t: number) => REST_WOB * (1 + 0.5 * Math.sin(t * 0.17))
/** Shape time runs faster and slower in turn, so the lobes change speed as well as size. */
const shapeTime = (t: number) => t * 1.15 + 1.4 * Math.sin(t * 0.13)

/** Where and how the entity should be in each mode, in coordinates of the chat page. */
function goal(mode: EntityMode, t: number, W: number, H: number, bar: Box, still: boolean): Goal {
  const cy = bar.top + bar.height / 2
  const base = { a: 1, arc: 0, fill: 0 }
  switch (mode) {
    case 'empty':
      return { ...base, x: W / 2, y: H * 0.4, hw: EMPTY_R, hh: EMPTY_R, r: EMPTY_R, wob: still ? 0 : restWob(t), br: 0.55 }
    case 'thinking': {
      const r = 9 + (still ? 0 : Math.sin(t * 5) * 1.5)
      return { ...base, x: bar.left + 30, y: cy, hw: r, hh: r, r, wob: still ? 0 : DESIGN_WOB + 0.1, br: 0.8, arc: 1 }
    }
    case 'searching': {
      const sx = still ? 0 : Math.sin(t * 1.7)
      const sp = still ? 0 : Math.abs(Math.cos(t * 1.7))
      const x = bar.left + bar.width / 2 + (bar.width / 2 - 50) * sx
      return { ...base, x, y: cy + 21, hw: 14 + 22 * sp, hh: 2.5, r: 2.5, wob: 0, br: 0.9, fill: 1 }
    }
    case 'answering':
      return { ...base, x: bar.left + 28, y: cy, hw: 13, hh: 13, r: 13, wob: still ? 0 : DESIGN_WOB * 0.7, br: 0.65 }
    case 'waiting':
      return { ...base, x: bar.left + 28, y: cy, hw: 15, hh: 15, r: 15, wob: 0, br: 1 }
    case 'docked':
      return { ...base, x: bar.left + 28, y: cy, hw: 13, hh: 13, r: 13, wob: still ? 0 : DESIGN_WOB * 0.7, br: 0.55 }
  }
}

const clamp = (v: number) => Math.max(0, Math.min(1, v))
const f1 = (n: number) => String(Math.round(n * 1000) / 1000)

/**
 * The Ka entity from the design, drawn as SVG: a wobbling outline that is the empty-home blob,
 * the thinking ring with its travelling arc, the search sweep under the box, and the small mark
 * docked in the composer. One rAF loop reads the mode from a ref, so a phase change never
 * restarts it; springs carry the shape between modes and a softer trail follows it.
 */
export function Entity({ mode }: { mode: EntityMode }) {
  const svg = useRef<SVGSVGElement>(null)
  const glowEl = useRef<HTMLDivElement>(null)
  const live = useRef({ mode, pending: 0 })
  const { data: pending = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  useEffect(() => {
    live.current = { mode, pending: Math.min(LIGHTS, pending.length) }
  }, [mode, pending.length])

  useEffect(() => {
    const el = svg.current
    const glow = glowEl.current
    const host = el?.parentElement
    if (!el || !glow || !host) return
    const layer = (k: string) => el.querySelector<SVGPathElement>(`[data-l="${k}"]`)!
    const L = Object.fromEntries(
      ['twinFill', 'twin', 'body', 'edge', 'arc', 'lightsGlow', 'lights'].map((k) => [k, layer(k)]),
    )
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const S: Record<string, Spring> = {}
    const T: Record<string, Spring> = {}
    const Lt: Spring[] = Array.from({ length: LIGHTS }, () => ({ x: 0, v: 0 }))
    let t = 0
    let last = performance.now()
    let raf = 0
    let light = document.documentElement.dataset.theme === 'light'
    const theme = new MutationObserver(() => {
      light = document.documentElement.dataset.theme === 'light'
    })
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    let tick = 0
    let drawn = '' // what the last frame drew, so a reduced-motion screen is not redrawn when nothing changed

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      tick += 1
      // the small docked mark barely moves: 30 frames a second is plenty and halves the work
      const quiet = live.current.mode !== 'empty' && live.current.mode !== 'thinking' && live.current.mode !== 'searching'
      if (quiet && tick % 2) return
      const dt = Math.min(0.034, Math.max(0, (now - last) / 1000))
      last = now
      t += dt
      const still = media.matches
      const hostBox = host.getBoundingClientRect()
      const c = host.querySelector('.composer')?.getBoundingClientRect()
      const bar: Box = c
        ? { left: c.left - hostBox.left, top: c.top - hostBox.top, width: c.width, height: c.height }
        : { left: 20, top: hostBox.height - 80, width: hostBox.width - 40, height: 56 }
      const { mode: m, pending: pend } = live.current
      const g = goal(m, t, hostBox.width, hostBox.height, bar, still)
      const first = !S.x
      for (const k of Object.keys(g) as (keyof Goal)[]) {
        S[k] ??= { x: g[k], v: 0 }
        spring(S[k], g[k], dt, 260, 24, still || first)
      }
      for (const k of ['x', 'y', 'hw', 'hh', 'r'] as const) {
        T[k] ??= { x: g[k], v: 0 }
        spring(T[k], g[k], dt, 70, 13, still || first)
      }
      const lit = m === 'empty' || m === 'answering' || m === 'waiting' || m === 'docked'
      Lt.forEach((s, i) => spring(s, lit && i < pend ? 1 : 0, dt, 110, 19, still))

      if (still) {
        const key = [m, pend, light, Math.round(hostBox.width), Math.round(hostBox.height), Math.round(bar.top)].join()
        if (key === drawn) return
        drawn = key
      }
      const shape: Geo = { x: S.x.x, y: S.y.x, hw: S.hw.x, hh: S.hh.x, r: S.r.x }
      const trail: Geo = { x: T.x.x, y: T.y.x, hw: T.hw.x, hh: T.hh.x, r: T.r.x }
      const a = clamp(S.a.x)
      const br = clamp(S.br.x)
      const wob = Math.max(0, S.wob.x)
      const fill = clamp(S.fill.x)
      const mn = Math.max(1, Math.min(shape.hw, shape.hh))
      const Lh = (light ? 30 : 44) + br * 22
      const lapis = `hsl(226,72%,${f1(Lh)}%)`
      const edge = `hsl(226,82%,${f1(Lh + (light ? 4 : 10))}%)`
      const sep =
        Math.abs(trail.x - shape.x) + Math.abs(trail.y - shape.y) + Math.abs(trail.hw - shape.hw) + Math.abs(trail.hh - shape.hh)
      const trailO = clamp(sep / 14)
      const st = still ? 0 : shapeTime(t)
      const d = shapePath(shape, wob, st)

      // the glow is one pre-blurred layer moved by transform, so the blur is not redrawn every frame
      glow.style.background = lapis
      glow.style.opacity = f1((0.1 + 0.4 * br) * (0.35 + 0.65 * a) * 0.45)
      glow.style.transform = `translate(${f1(shape.x - 50)}px,${f1(shape.y - 50)}px) scale(${f1(shape.hw / 50)},${f1(shape.hh / 50)})`
      L.twinFill.setAttribute('fill', lapis)
      L.twin.setAttribute('stroke', edge)
      if (trailO > 0.01) {
        const td = shapePath(trail, wob, st)
        L.twinFill.setAttribute('d', td)
        L.twin.setAttribute('d', td)
      }
      L.twinFill.setAttribute('opacity', f1(0.16 * trailO * (0.3 + 0.7 * a)))
      L.twin.setAttribute('opacity', f1(0.6 * trailO))
      L.body.setAttribute('d', d)
      L.body.setAttribute('fill', lapis)
      L.body.setAttribute('opacity', f1(a * (0.1 + 0.75 * fill)))
      L.edge.setAttribute('d', d)
      L.edge.setAttribute('stroke', edge)
      L.edge.setAttribute('stroke-width', f1(Math.min(1.5 + 2.5 * a, Math.max(1.5, mn * 0.4))))
      const arcO = clamp(S.arc.x)
      L.arc.setAttribute('d', arcO > 0.01 ? arcPath(shape, t) : 'M0 0')
      L.arc.setAttribute('opacity', f1(arcO))
      const ld = lightsPath(shape, Lt.map((s) => s.x), st, mn * wob, still)
      L.lightsGlow.setAttribute('d', ld)
      L.lights.setAttribute('d', ld)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      theme.disconnect()
    }
  }, [])

  return (
    <>
      <div ref={glowEl} className="entity-glow" aria-hidden="true" />
      <svg ref={svg} className="entity" data-mode={mode} role="img" aria-label="Ka">
        <path data-l="twinFill" />
        <path data-l="twin" fill="none" strokeWidth={1.5} />
        <path data-l="body" />
        <path data-l="edge" fill="none" />
        <path data-l="arc" fill="none" stroke="hsl(226,95%,84%)" strokeWidth={4} strokeLinecap="round" />
        <path data-l="lightsGlow" fill="#F1F5FF" opacity={0.5} style={{ filter: 'blur(4px)' }} />
        <path data-l="lights" fill="#F1F5FF" />
      </svg>
    </>
  )
}
