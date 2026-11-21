import { expect, test, vi } from 'vitest'
import { watchKeyboard } from './viewport'

function fakeWindow(innerHeight: number) {
  const vv = Object.assign(new EventTarget(), { height: innerHeight, offsetTop: 0, scale: 1 })
  const scrollTo = vi.fn()
  const win = { innerHeight, visualViewport: vv, scrollTo } as unknown as Window
  return { win, vv, scrollTo }
}

test('keyboard height in, offset cleared out', () => {
  const { win, vv, scrollTo } = fakeWindow(852)
  const stop = watchKeyboard(win)
  vv.height = 516
  vv.dispatchEvent(new Event('resize'))
  expect(document.documentElement.style.getPropertyValue('--kb')).toBe('336px')
  vv.height = 852
  vv.dispatchEvent(new Event('resize'))
  expect(document.documentElement.style.getPropertyValue('--kb')).toBe('0px')
  expect(scrollTo).toHaveBeenCalledWith(0, 0)
  stop()
})

test('pinch zoom is not a keyboard', () => {
  const { win, vv } = fakeWindow(852)
  const stop = watchKeyboard(win)
  Object.assign(vv, { scale: 2, height: 426 })
  vv.dispatchEvent(new Event('resize'))
  expect(document.documentElement.style.getPropertyValue('--kb')).toBe('0px')
  stop()
})
