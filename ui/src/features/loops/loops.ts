import type { LoopTask, TaskRun, Trigger } from '../../lib/api'

const DAYS: Record<string, string> = {
  mon: 'Mondays', tue: 'Tuesdays', wed: 'Wednesdays', thu: 'Thursdays', fri: 'Fridays', sat: 'Saturdays', sun: 'Sundays',
}

const hm = (h: number, m: number) => `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`

export function describeTrigger(t: Trigger): string {
  if (t.type === 'cron') return t.day_of_week ? `${DAYS[t.day_of_week] ?? t.day_of_week} at ${hm(t.hour, t.minute)}` : `daily at ${hm(t.hour, t.minute)}`
  const every = t.minutes % 60 === 0 ? `${t.minutes / 60} h` : `${t.minutes} min`
  return t.type === 'folder' ? `checks Drive every ${every}` : `every ${every}`
}

/** When it runs next, in words. Interval tasks count from their last check-in. */
export function nextRunLabel(task: LoopTask, now: Date): string {
  if (task.status === 'paused') return 'paused'
  const t = task.trigger
  if (t.type === 'cron') return describeTrigger(t)
  const from = new Date(task.last_checkin ?? task.created_at).getTime()
  const left = Math.round((from + t.minutes * 60_000 - now.getTime()) / 60_000)
  if (left <= 0) return 'due now'
  return left < 60 ? `in ${left} min` : `in ${Math.round(left / 60)} h`
}

/** A hint, never automatic: a shadow task with five approvals and no rejections. */
export function canGoDirect(task: LoopTask): boolean {
  return task.mode === 'shadow' && task.approved >= 5 && task.rejected === 0
}

export type TriggerForm = { every: 'hours' | 'daily' | 'weekly'; hours: number; time: string; day: string }

export function triggerFromForm(f: TriggerForm): Trigger {
  if (f.every === 'hours') return { type: 'interval', minutes: Math.max(1, Math.round(f.hours)) * 60 }
  const [h, m] = f.time.split(':').map(Number)
  const at = { type: 'cron' as const, hour: h || 0, minute: m || 0 }
  return f.every === 'weekly' ? { ...at, day_of_week: f.day || 'mon' } : at
}

/** "Run now" returns at once; the run is done when a run newer than the last one known has ended. */
export function runSettled(runs: Pick<TaskRun, 'id' | 'finished_at'>[], lastKnown: number): boolean {
  return runs.some((r) => r.id > lastKnown && r.finished_at !== null)
}
