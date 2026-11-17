import { useQuery } from '@tanstack/react-query'
import { api, keys, type IntakeJob } from '../../lib/api'

/** Polls a job once a second until it is done or failed. */
export function useIntakeJob(jobId: string | null) {
  return useQuery<IntakeJob>({
    queryKey: keys.intake(jobId ?? 'none'),
    queryFn: () => api.intakeJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data && ['done', 'failed'].includes(q.state.data.status) ? false : 1000),
  })
}
