import { expect, test } from 'vitest'
import type { LoopTask, TaskRun } from '../../lib/api'
import { canGoDirect, describeTrigger, nextRunLabel, runSettled, triggerFromForm } from './loops'

const base = {
  id: 'T-1', name: 'n', kind: 'agent', builtin: null, brief: 'b', toolkits: [], mode: 'shadow',
  status: 'active', created_by: 'ui', created_at: '2031-04-05T08:00:00', last_checkin: null,
  last_run: null, approved: 0, rejected: 0,
} as const

const task = (over: Partial<LoopTask>): LoopTask => ({ ...base, trigger: { type: 'interval', minutes: 60 }, ...over }) as LoopTask

test('next run for an interval counts from the last check-in', () => {
  const t = task({ last_checkin: '2031-04-05T10:00:00' })
  expect(nextRunLabel(t, new Date('2031-04-05T10:30:00'))).toBe('in 30 min')
  expect(nextRunLabel(task({ status: 'paused' }), new Date())).toBe('paused')
  expect(nextRunLabel(task({ trigger: { type: 'cron', hour: 8, minute: 0, day_of_week: 'mon' } }), new Date())).toBe('Mondays at 08:00')
})

test('direct mode is only suggested after a clean record', () => {
  expect(canGoDirect(task({ approved: 5, rejected: 0 }))).toBe(true)
  expect(canGoDirect(task({ approved: 9, rejected: 1 }))).toBe(false)
  expect(canGoDirect(task({ approved: 4 }))).toBe(false)
  expect(canGoDirect(task({ approved: 5, mode: 'direct' }))).toBe(false)
})

test('the form makes a valid trigger', () => {
  expect(triggerFromForm({ every: 'hours', hours: 3, time: '08:00', day: '' })).toEqual({ type: 'interval', minutes: 180 })
  expect(triggerFromForm({ every: 'daily', hours: 1, time: '07:30', day: '' })).toEqual({ type: 'cron', hour: 7, minute: 30 })
  expect(triggerFromForm({ every: 'weekly', hours: 1, time: '08:00', day: 'mon' })).toEqual({ type: 'cron', hour: 8, minute: 0, day_of_week: 'mon' })
  expect(describeTrigger({ type: 'folder', minutes: 180, source: 'drive' })).toBe('checks Drive every 3 h')
})

test('a manual run counts as finished only once a newer run has an end time', () => {
  const r = (id: number, finished: string | null) => ({ id, finished_at: finished }) as TaskRun
  expect(runSettled([r(4, '2031-04-05T10:00:00')], 4)).toBe(false) // the old run
  expect(runSettled([r(5, null), r(4, 'x')], 4)).toBe(false) // the new one is still going
  expect(runSettled([r(5, '2031-04-05T10:01:00')], 4)).toBe(true)
})
