import { expect, test, vi } from 'vitest'
import { followGrowth, nearBottom } from './follow'

test('follows only within 80px of the bottom', () => {
  expect(nearBottom({ scrollTop: 920, scrollHeight: 1500, clientHeight: 500 })).toBe(true) // 80 left
  expect(nearBottom({ scrollTop: 900, scrollHeight: 1500, clientHeight: 500 })).toBe(false) // 100 left
})

test('growing content pulls the view down only while following', () => {
  let fire = () => {}
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(cb: () => void) {
        fire = cb
      }
      observe() {}
      disconnect() {}
    },
  )
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', { value: 900 })
  let on = true
  const stop = followGrowth(el, document.createElement('div'), () => on)
  fire()
  expect(el.scrollTop).toBe(900)
  el.scrollTop = 100
  on = false
  fire()
  expect(el.scrollTop).toBe(100)
  stop()
  vi.unstubAllGlobals()
})

test('the scroller shrinking (keyboard opening) is watched too', () => {
  const watched: Element[] = []
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe(t: Element) {
        watched.push(t)
      }
      disconnect() {}
    },
  )
  const el = document.createElement('div')
  const content = document.createElement('div')
  followGrowth(el, content, () => true)
  expect(watched).toEqual([content, el])
  vi.unstubAllGlobals()
})
