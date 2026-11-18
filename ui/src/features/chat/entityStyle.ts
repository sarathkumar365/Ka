import type { Phase } from './state'

/** Port of `entity()` in Design/extracted/app.html: geometry per phase, inside the 720px chat area. */
export type EntityMode = 'empty' | 'typing' | 'thinking' | 'searching' | 'answering' | 'waiting' | 'docked'

export function entityMode(phase: Phase, hasItems: boolean, typing: boolean): EntityMode {
  if (phase === 'idle') return hasItems ? 'docked' : typing ? 'typing' : 'empty'
  return phase
}

type EntityStyle = {
  l: string
  t: string
  w: string
  h: string
  r: string
  bw: string
  bc: string
  bg: string
  sh: string
  tf: string
  tr: string // the entity's transition
  tr2: string // the trailing copy's transition: slower, so it lags behind
}

// The design wobbles the empty blob by 4%; the owner asked for more, so 9%.
const WOBBLE = 9

function tr(d: number, ease: string, left?: string, rad?: string): string {
  const g = `${d}ms ${ease}`
  return (
    `left ${left ?? g}, top ${g}, width ${g}, height ${g}, border-radius ${rad ?? g}, ` +
    'border-width 300ms ease, background-color 300ms ease, border-color 300ms ease, box-shadow 300ms ease, transform 2400ms ease-in-out'
  )
}

/** `beat` ticks on the design's 2.4s cycle; `sw` flips the search bar between its two ends. */
export function entityStyle(mode: EntityMode, beat: number, sw: boolean): EntityStyle {
  const bar = 'calc(100% - 80px)' // top of the 56px composer, which sits 24px above the bottom
  const e = {
    l: '16px',
    t: 'calc(100% - 64px)',
    w: '24px',
    h: '24px',
    r: '12px',
    bw: '3px',
    bc: 'var(--lapis)',
    bg: 'transparent',
    sh: '0 0 0 0 transparent',
    tf: 'scale(1)',
  }
  let left: string | undefined
  let rad: string | undefined
  if (mode === 'empty') {
    const a = WOBBLE * Math.sin(beat * 1.7)
    const c = WOBBLE * Math.cos(beat * 2.3)
    const p = (n: number) => `${Math.round(n * 1000) / 1000}%`
    Object.assign(e, { l: 'calc(50% - 76px)', t: 'calc(40% - 76px)', w: '152px', h: '152px', bw: '4px' })
    e.r = `${p(50 + a)} ${p(50 - a)} ${p(50 + c)} ${p(50 - c)} / ${p(50 - c)} ${p(50 + a)} ${p(50 - a)} ${p(50 + c)}`
    e.tf = beat % 2 ? 'scale(1.025)' : 'scale(1)'
    rad = '1200ms ease-in-out'
  }
  if (mode === 'typing') Object.assign(e, { l: '0px', t: bar, w: '100%', h: '56px', bw: '2px', bg: 'var(--lapis-wash)' })
  // thinking: the element shrinks into the ring's place and fades out; ThinkingRing draws the ring
  if (mode === 'thinking') Object.assign(e, { l: '18px', t: 'calc(100% - 62px)', w: '20px', h: '20px', r: '10px', bc: 'transparent' })
  if (mode === 'searching') {
    Object.assign(e, { l: sw ? 'calc(100% - 64px)' : '20px', t: 'calc(100% - 36px)', w: '44px', h: '5px', r: '3px', bw: '2.5px', bg: 'var(--lapis)' })
    left = '900ms ease-in-out'
  }
  if (mode === 'waiting')
    Object.assign(e, { l: '15px', t: 'calc(100% - 65px)', w: '26px', h: '26px', r: '13px', bc: 'var(--lapis-hi)', sh: '0 0 0 5px var(--lapis-wash)' })
  return {
    ...e,
    tr: tr(440, 'var(--S)', left, rad),
    tr2: tr(700, 'var(--E)', left ? '900ms ease-in-out 130ms' : undefined, rad),
  }
}
