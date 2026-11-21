import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, keys, type LoopTask, type NewLoop } from '../../lib/api'
import { runSettled } from './loops'

export function useLoops() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: keys.loops, queryFn: api.loops })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.loops })
    qc.invalidateQueries({ queryKey: keys.activity })
  }
  const create = useMutation({ mutationFn: (b: NewLoop) => api.createLoop(b), onSuccess: refresh })
  const update = useMutation({
    mutationFn: (v: { id: string; body: Partial<Pick<LoopTask, 'status' | 'mode'>> }) => api.updateLoop(v.id, v.body),
    onSuccess: refresh,
  })
  const remove = useMutation({ mutationFn: (id: string) => api.deleteLoop(id), onSuccess: refresh })
  // Run now returns at once; poll that loop's runs until the new one ends (at most 5 minutes).
  const [watching, setWatching] = useState<{ id: string; after: number; until: number } | null>(null)
  const run = useMutation({
    mutationFn: (id: string) => api.runLoop(id),
    onSuccess: (_, id) => {
      const last = list.data?.find((t) => t.id === id)?.last_run?.id ?? 0
      setWatching({ id, after: last, until: Date.now() + 5 * 60_000 })
    },
  })
  useQuery({
    queryKey: keys.runs(watching?.id ?? ''),
    queryFn: async () => {
      const w = watching!
      const runs = await api.loopRuns(w.id)
      if (runSettled(runs, w.after) || Date.now() > w.until) {
        setWatching(null)
        refresh()
      }
      return runs
    },
    enabled: watching !== null,
    refetchInterval: 2000,
  })
  return { list, create, update, remove, run, runningId: watching?.id ?? null }
}
