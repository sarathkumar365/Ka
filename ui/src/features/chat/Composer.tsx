import { useEffect, useRef, useState } from 'react'
import { registerDraft, takeDraft } from '../auth/session'
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
  useEffect(() => {
    const d = takeDraft() // a message left unsent when the session ended
    if (d) setText(d)
  }, [])
  const latest = useRef(text)
  useEffect(() => {
    latest.current = text
  }, [text])
  useEffect(() => {
    registerDraft(() => latest.current)
    return () => registerDraft(null)
  }, [])
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
