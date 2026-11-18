import { type MemoryEntry, toItems } from './memory'

export type BasicsDraft = { name: string; where: string; role: string }
export type Draft = { basics: BasicsDraft; files: File[]; memory: MemoryEntry[] }

export function emptyDraft(): Draft {
  return { basics: { name: '', where: '', role: '' }, files: [], memory: [{ id: 1, source: 'Claude', text: '' }] }
}

export const basicsFilled = (b: BasicsDraft) => [b.name, b.where, b.role].some((v) => v.trim())

export function hasInput(d: Draft): boolean {
  return basicsFilled(d.basics) || d.files.length > 0 || toItems(d.memory).length > 0
}

/** The one request Send to Ka makes: files, basics JSON when filled, memory JSON when any text. */
export function toForm(d: Draft): FormData {
  const form = new FormData()
  d.files.forEach((f) => form.append('files', f))
  if (basicsFilled(d.basics)) {
    const [city = '', region = '', country = ''] = d.basics.where.split(',').map((s) => s.trim())
    form.append('basics', JSON.stringify({ name: d.basics.name.trim(), city, region, country, role: d.basics.role.trim() }))
  }
  const items = toItems(d.memory)
  if (items.length) form.append('memory', JSON.stringify(items))
  return form
}

export function summaryLine(r: { cards: number; jobs: number; highlights: number; memories: number }): string {
  return `${r.cards} card(s) to review: ${r.jobs} job(s), ${r.highlights} highlight(s), ${r.memories} memory item(s).`
}
