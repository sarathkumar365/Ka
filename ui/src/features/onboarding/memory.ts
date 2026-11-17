export const ASSISTANTS = ['Claude', 'ChatGPT', 'Gemini', 'Other'] as const
export const MAX_SOURCES = 5

export type MemoryEntry = { id: number; source: string; text: string }

/** What the server gets: only filled boxes, assistant names in lower case. */
export function toItems(entries: MemoryEntry[]): { source: string; text: string }[] {
  return entries.filter((e) => e.text.trim()).map((e) => ({ source: e.source.toLowerCase(), text: e.text }))
}

/** The next assistant not used yet, so a second box defaults to ChatGPT after Claude. */
export function nextAssistant(entries: MemoryEntry[]): string {
  return ASSISTANTS.find((a) => !entries.some((e) => e.source === a)) ?? 'Other'
}
