import type { ReactNode } from 'react'

/** 20px line icons from the design (Design/extracted/app.html), stroke set by `.ic`. */
const shapes = {
  history: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4l2.5 2" />
    </>
  ),
  inbox: (
    <>
      <path d="M3 11l2-6h10l2 6v4H3z" />
      <path d="M3 11h4l1 2h4l1-2h4" />
    </>
  ),
  sliders: (
    <>
      <path d="M3 6h8M15 6h2M3 14h2M9 14h8" />
      <circle cx="13" cy="6" r="2" />
      <circle cx="7" cy="14" r="2" />
    </>
  ),
  plus: <path d="M10 4v12M4 10h12" />,
  close: <path d="M5 5l10 10M15 5L5 15" />,
  chevron: <path d="M8 6l4 4-4 4" />,
  send: <path d="M10 15V5M6 9l4-4 4 4" />,
  check: <path d="M5 10.5l3.2 3L15 7" />,
  dash: <path d="M5 10h10" />,
} satisfies Record<string, ReactNode>

export function Icon({ name, size = 20 }: { name: keyof typeof shapes; size?: number }) {
  return (
    <svg className="ic" width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
      {shapes[name]}
    </svg>
  )
}
