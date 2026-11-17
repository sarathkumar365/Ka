const paths = {
  menu: 'M3 6h14M3 10h14M3 14h14',
  bell: 'M5 8a5 5 0 0110 0c0 4 1.5 5 1.5 5h-13S5 12 5 8zM8.5 16a1.5 1.5 0 003 0',
  gear: 'M10 7a3 3 0 100 6 3 3 0 000-6zM10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4',
  plus: 'M10 4v12M4 10h12',
  close: 'M5 5l10 10M15 5L5 15',
  chevron: 'M8 6l4 4-4 4',
  send: 'M10 16V4M5 9l5-5 5 5',
  check: 'M4 10l4 4 8-8',
  tool: 'M4 6h12M4 10h12M4 14h7',
} as const

export function Icon({ name, size = 20 }: { name: keyof typeof paths; size?: number }) {
  return (
    <svg className="ic" width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  )
}
