import { ASSISTANTS, MAX_SOURCES, type MemoryEntry, nextAssistant } from './memory'

const PROMPT =
  'List everything you have remembered about me: facts about my life and work, my preferences, and any rules I asked you to follow. One item per line. Do not guess; include only what you actually know.'

export function StepMemory({ entries, onChange }: { entries: MemoryEntry[]; onChange: (e: MemoryEntry[]) => void }) {
  const update = (id: number, patch: Partial<MemoryEntry>) =>
    onChange(entries.map((e) => (e.id === id ? { ...e, ...patch } : e)))
  const add = () =>
    onChange([...entries, { id: Math.max(0, ...entries.map((e) => e.id)) + 1, source: nextAssistant(entries), text: '' }])
  return (
    <div className="step">
      <h1>Bring memory from other assistants</h1>
      <p className="lead">
        Ask each assistant you use to export what it remembers about you, then paste each answer in its own box.
      </p>
      <div className="sub">
        Ask it: <em>{PROMPT}</em>{' '}
        <button className="linkbtn" onClick={() => navigator.clipboard?.writeText(PROMPT)}>
          Copy the question
        </button>
      </div>
      {entries.map((e) => (
        <div key={e.id} className="col" style={{ gap: 8 }}>
          <div className="row" style={{ gap: 8, alignItems: 'end' }}>
            <label className="field" style={{ flex: 1 }}>
              <span>Assistant</span>
              <select value={e.source} onChange={(ev) => update(e.id, { source: ev.target.value })}>
                {ASSISTANTS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            {entries.length > 1 && (
              <button className="linkbtn" onClick={() => onChange(entries.filter((x) => x.id !== e.id))}>
                Remove
              </button>
            )}
          </div>
          <label className="field">
            <span>Pasted memory export from {e.source}</span>
            <textarea rows={7} value={e.text} maxLength={60000} onChange={(ev) => update(e.id, { text: ev.target.value })} />
          </label>
        </div>
      ))}
      {entries.length < MAX_SOURCES && (
        <div>
          <button className="linkbtn" onClick={add}>
            Add another assistant
          </button>
        </div>
      )}
      <div className="sub">Nothing is sent yet. The same fact from two assistants is kept once.</div>
    </div>
  )
}
