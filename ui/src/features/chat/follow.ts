type Scroll = { scrollTop: number; scrollHeight: number; clientHeight: number }

/** The reader is at (or close to) the end of the thread, so new text may pull the view down. */
export function nearBottom(el: Scroll, slack = 80): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= slack
}

/**
 * The answer types itself out without any new chat state, so watch the thread's height (and the
 * scroller's own, which the keyboard changes) instead:
 * while the reader follows, each growth keeps the end in view. Returns the stop function.
 */
export function followGrowth(el: HTMLElement, content: HTMLElement, following: () => boolean): () => void {
  if (typeof ResizeObserver === 'undefined') return () => {}
  const ro = new ResizeObserver(() => {
    if (following()) el.scrollTop = el.scrollHeight
  })
  ro.observe(content)
  ro.observe(el) // the scroller shrinks when the keyboard opens: keep the end in view then too
  return () => ro.disconnect()
}
