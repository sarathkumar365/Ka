import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../lib/api'

export function StepBasics() {
  const [name, setName] = useState('')
  const [where, setWhere] = useState('')
  const [role, setRole] = useState('')
  const save = useMutation({
    mutationFn: () => {
      const [city = '', region = '', country = ''] = where.split(',').map((s) => s.trim())
      return api.submitBasics({ name, city, region, country, role })
    },
  })
  const filled = name.trim() || where.trim() || role.trim()
  return (
    <div className="step">
      <h1>First, the basics</h1>
      <p className="lead">Only what you want Ka to know. You can change any of it later.</p>
      <label className="field">
        <span>What should Ka call you?</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span>Where do you live? (city, region, country)</span>
        <input value={where} onChange={(e) => setWhere(e.target.value)} />
      </label>
      <label className="field">
        <span>What do you do for work?</span>
        <input value={role} onChange={(e) => setRole(e.target.value)} />
      </label>
      {save.isError && (
        <div className="notice" role="alert">
          {(save.error as Error).message}
        </div>
      )}
      {save.isSuccess && <div className="sub">Added to Pending for your approval.</div>}
      <div>
        <button className="secondary" disabled={!filled || save.isPending} onClick={() => save.mutate()}>
          Add to Pending
        </button>
      </div>
    </div>
  )
}
