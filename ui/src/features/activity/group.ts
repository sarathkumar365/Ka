import type { ActivityRow } from '../../lib/api'

const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()

export function groupByDay(rows: ActivityRow[], now: Date): { label: string; rows: ActivityRow[] }[] {
  const groups: { label: string; rows: ActivityRow[] }[] = []
  for (const r of rows) {
    const at = new Date(r.at)
    const diff = Math.round((day(now) - day(at)) / 86_400_000)
    const label =
      diff === 0
        ? 'Today'
        : diff === 1
          ? 'Yesterday'
          : at.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
    const last = groups[groups.length - 1]
    if (last?.label === label) last.rows.push(r)
    else groups.push({ label, rows: [r] })
  }
  return groups
}
