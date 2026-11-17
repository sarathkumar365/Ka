export function toggleItem(selected: string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
}

type CardState = { ready: boolean; blocked: string | null; section?: string; items: { id: string }[] }

/** A card can be approved when its prerequisites are decided, it is not blocked, and (for a job) the job line is ticked. */
export function canApprove(card: CardState, selected: string[]): boolean {
  if (!card.ready || card.blocked || selected.length === 0) return false
  if (card.section === 'job' && !selected.includes(card.items[0]?.id)) return false
  return true
}
