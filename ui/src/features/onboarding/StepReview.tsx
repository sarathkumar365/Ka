import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, keys } from '../../lib/api'

export function StepReview() {
  const { data = [] } = useQuery({ queryKey: keys.pending, queryFn: api.pending })
  return (
    <div className="step">
      <h1>Review before anything is saved</h1>
      <p className="lead">
        Everything Ka found is waiting in Pending. Nothing becomes part of your data until you approve it.
      </p>
      <div>
        <Link className="secondary linklike" to="/pending">
          {data.length ? `Open Pending (${data.length} waiting)` : 'Open Pending'}
        </Link>
      </div>
    </div>
  )
}
