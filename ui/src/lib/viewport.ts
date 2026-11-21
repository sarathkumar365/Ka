/**
 * iOS does not shrink the layout when the keyboard opens; it slides the page instead and can
 * leave it slid after the keyboard closes. Publish the keyboard's height as --kb so the composer
 * can sit on top of it, and put the page back once the keyboard is gone.
 */
export function watchKeyboard(win: Window): () => void {
  const vv = win.visualViewport
  if (!vv) return () => {}
  const root = document.documentElement
  let open = false
  const update = () => {
    // zoomed in, the visual viewport is small because of the zoom, not a keyboard
    const zoomed = Math.abs((vv.scale ?? 1) - 1) > 0.01
    const kb = zoomed ? 0 : Math.max(0, Math.round(win.innerHeight - vv.height - vv.offsetTop))
    root.style.setProperty('--kb', `${kb}px`)
    if (kb === 0 && open) win.scrollTo(0, 0)
    open = kb > 0
  }
  vv.addEventListener('resize', update)
  vv.addEventListener('scroll', update)
  return () => {
    vv.removeEventListener('resize', update)
    vv.removeEventListener('scroll', update)
  }
}
