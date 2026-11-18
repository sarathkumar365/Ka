/** Geometry of the design board's thinking ring; see ThinkingRing.tsx. */
const N = 96
const WOBBLE = 0.155 // the board's rest wobble plus its +0.1 for thinking

const disp = (s: number, t: number, scale: number) => {
  const a = s * 2 * Math.PI
  return scale * (Math.sin(a * 2 + t * 0.9) * 0.6 + Math.sin(a * 3 - t * 0.6 + 1.7) * 0.4 + Math.sin(a * 5 + t * 1.3) * 0.18)
}

/** Point on a circle at perimeter fraction s, starting at the top, with its outward normal. */
const pt = (r: number, s: number) => {
  const an = s * 2 * Math.PI - Math.PI / 2
  return [r * Math.cos(an), r * Math.sin(an), Math.cos(an), Math.sin(an)] as const
}

const f1 = (n: number) => (Math.round(n * 10) / 10).toString()

export function ringPath(t: number, still: boolean): { ring: string; arc: string } {
  const r = 9 + (still ? 0 : Math.sin(t * 5) * 1.5)
  const scale = still ? 0 : r * WOBBLE
  let ring = ''
  for (let i = 0; i <= N; i++) {
    const s = i / N
    const [x, y, nx, ny] = pt(r, s)
    const d = disp(s, t, scale)
    ring += `${i ? 'L' : 'M'}${f1(x + nx * d)} ${f1(y + ny * d)}`
  }
  let arc = ''
  const u = still ? 0 : t * 0.45
  for (let i = 0; i <= 24; i++) {
    const [x, y] = pt(r, u + (i / 24) * 0.28)
    arc += `${i ? 'L' : 'M'}${f1(x)} ${f1(y)}`
  }
  return { ring: ring + 'Z', arc }
}
