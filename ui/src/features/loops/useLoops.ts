import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, keys, type LoopTask, type NewLoop } from '../../lib/api'

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
  const run = useMutation({
    mutationFn: (id: string) => api.runLoop(id),
    onSuccess: (_, id) => {
      refresh()
      qc.invalidateQueries({ queryKey: keys.runs(id) })
    },
  })
  return { list, create, update, remove, run }
}
