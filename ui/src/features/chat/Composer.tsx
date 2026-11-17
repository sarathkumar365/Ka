import { useState } from 'react'
import { Icon } from '../../lib/icons'

export function Composer({ disabled, onSend, docked }: { disabled: boolean; onSend: (t: string) => void; docked: boolean }) {
  const [text, setText] = useState('')
  const submit = () => {
    const t = text.trim()
    if (!t || disabled) return
    setText('')
    onSend(t)
  }
  return (
    <div className="composer" data-docked={docked}>
      <input
        type="text"
        aria-label="Message Ka"
        placeholder="Ask Ka"
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
