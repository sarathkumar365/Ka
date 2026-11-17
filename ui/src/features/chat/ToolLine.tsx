import { useState } from 'react'
import { Icon } from '../../lib/icons'

const LABELS: Record<string, string> = {
  finance_summary: 'Looked at your spending',
  search_transactions: 'Searched transactions',
  sum_transactions: 'Added up transactions',
  list_statements: 'Listed statements',
  search_conversations: 'Searched past chats',
  get_jobs: 'Read your jobs',
  get_profile: 'Read your profile',
  propose_change: 'Proposed a change',
  propose_memory: 'Suggested a memory',
  remember: 'Saved a memory',
  import_statement: 'Prepared a statement import',
}

function rows(result?: string): number | null {
  try {
    const v = JSON.parse(result ?? '')
    return Array.isArray(v) ? v.length : null
  } catch {
    return null
  }
}

export function ToolLine({ name, args, result }: { name: string; args: Record<string, unknown>; result?: string }) {
  const [open, setOpen] = useState(false)
  const n = rows(result)
  const label = (LABELS[name] ?? `Used ${name}`) + (n === null ? '' : `, ${n} row${n === 1 ? '' : 's'}`)
  return (
    <div className="toolline">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="tool" size={16} />
        <span>{result === undefined ? `${label}…` : label}</span>
      </button>
      {open && (
        <pre className="mono detail">
          {JSON.stringify(args)}
          {result !== undefined && `\n→ ${result.length > 600 ? result.slice(0, 600) + '…' : result}`}
        </pre>
      )}
    </div>
  )
}
