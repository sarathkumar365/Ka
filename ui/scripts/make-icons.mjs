// Renders the PWA icons from one SVG. Run: node scripts/make-icons.mjs
import sharp from 'sharp'

const BG = '#1B1C1F'
const ring = (size, pad) => {
  const r = (size - pad * 2) * 0.3
  const w = size * 0.07
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <rect width="${size}" height="${size}" fill="${BG}"/>
      <ellipse cx="${size / 2}" cy="${size / 2}" rx="${r * 1.04}" ry="${r}" fill="none" stroke="#6384F0" stroke-width="${w}"/>
    </svg>`,
  )
}
const out = (name, size, pad = 0) => sharp(ring(size, pad)).png().toFile(`public/icons/${name}`)
await Promise.all([
  out('icon-192.png', 192),
  out('icon-512.png', 512),
  out('maskable-512.png', 512, 64),
  out('apple-touch-icon.png', 180),
])
