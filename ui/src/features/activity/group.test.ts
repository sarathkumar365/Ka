import { expect, test } from 'vitest'
import type { ActivityRow } from '../../lib/api'
import { groupByDay } from './group'

const row = (id: number, at: string): ActivityRow => ({ id, at, kind: 'read', text: `t${id}`, conversation_id: null })
const now = new Date(2031, 3, 10, 12, 0)

test('groups newest-first rows into Today, Yesterday and a dated label', () => {
  const g = groupByDay(
    [row(3, '2031-04-10T09:42:00'), row(2, '2031-04-10T08:00:00'), row(1, '2031-04-09T18:30:00'), row(0, '2031-04-07T10:00:00')],
    now,
  )
  expect(g.map((x) => x.label).slice(0, 2)).toEqual(['Today', 'Yesterday'])
  expect(g[0].rows.map((r) => r.id)).toEqual([3, 2])
  expect(g[2].label).not.toMatch(/Today|Yesterday/)
  expect(groupByDay([], now)).toEqual([])
})
