import { useState } from 'react'
import { Icon } from '../../lib/icons'

export function Composer({
  disabled,
  onSend,
  docked,
  placeholder,
  chrome,
  onFocusChange,
}: {
  disabled: boolean
  onSend: (t: string) => void
  docked: boolean
  placeholder: string
  chrome: 'on' | 'dim' | 'off'
  /** focused, or still holding text after losing focus: the design's "typing" phase */
  onFocusChange: (typing: boolean) => void
}) {
  const [text, setText] = useState('')
  const submit = () => {
    const t = text.trim()
    if (!t || disabled) return
    setText('')
    onFocusChange(false)
    onSend(t)
  }
  return (
    <div className="composer" data-docked={docked} data-chrome={chrome} data-busy={disabled}>
      <input
        type="text"
        aria-label="Message Ka"
        placeholder={placeholder}
        value={text}
        enterKeyHint="send"
        onChange={(e) => setText(e.target.value)}
        onFocus={() => onFocusChange(true)}
        onBlur={() => onFocusChange(text.trim() !== '')}
        onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && submit()}
      />
      <button type="button" aria-label="Send" onClick={submit} disabled={disabled || !text.trim()}>
        <Icon name="send" />
      </button>
    </div>
  )
}
