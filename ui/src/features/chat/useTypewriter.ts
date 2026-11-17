import { useEffect, useState } from 'react'

const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/** Reveals `text` about 2 characters per 24 ms; instant when disabled or motion is reduced. */
export function useTypewriter(text: string, enabled: boolean): string {
  const [n, setN] = useState(enabled && !reduced() ? 0 : text.length)
  useEffect(() => {
    if (!enabled || reduced()) {
      setN(text.length)
      return
    }
    setN(0)
    let i = 0
    const t = setInterval(() => {
      i = Math.min(i + 2, text.length)
      setN(i)
      if (i >= text.length) clearInterval(t)
    }, 24)
    return () => clearInterval(t)
  }, [text, enabled])
  return text.slice(0, n)
}
