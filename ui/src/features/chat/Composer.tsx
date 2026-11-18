import { useState } from 'react'
import { Icon } from '../../lib/icons'

export function Composer({
  disabled,
  onSend,
  docked,
  placeholder,
  dim,
}: {
  disabled: boolean
  onSend: (t: string) => void
  docked: boolean
  placeholder: string
  dim: boolean
}) {
  const [text, setText] = useState('')
  const submit = () => {
    const t = text.trim()
    if (!t || disabled) return
    setText('')
    onSend(t)
  }
  return (
    <div className="composer" data-docked={docked} data-dim={dim} data-busy={disabled}>
      <input
        type="text"
        aria-label="Message Ka"
        placeholder={placeholder}
        value={text}
        enterKeyHint="send"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && submit()}
      />
      <button type="button" aria-label="Send" onClick={submit} disabled={disabled || !text.trim()}>
        <Icon name="send" />
      </button>
    </div>
  )
}
