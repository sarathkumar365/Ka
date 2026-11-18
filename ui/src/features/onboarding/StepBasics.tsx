import type { BasicsDraft } from './draft'

export function StepBasics({ value, onChange }: { value: BasicsDraft; onChange: (v: BasicsDraft) => void }) {
  const set = (k: keyof BasicsDraft) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="step">
      <h1>First, the basics</h1>
      <p className="lead">Only what you want Ka to know. You can change any of it later.</p>
      <label className="field">
        <span>What should Ka call you?</span>
        <input value={value.name} onChange={set('name')} />
      </label>
      <label className="field">
        <span>Where do you live?</span>
        <input value={value.where} onChange={set('where')} />
      </label>
      <label className="field">
        <span>What do you do for work?</span>
        <input value={value.role} onChange={set('role')} />
      </label>
    </div>
  )
}
