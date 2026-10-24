import { Link } from 'react-router-dom'
import { Card, Empty, ErrorBox, Loading, StatusBadge, Tag } from '../components/ui'
import TaskList from '../components/TaskList'
import { certaintyLabel, km, usageText, when } from '../format'
import { useApi } from '../hooks'
import type { Bike, BrakeRow, ChainRow, RideRow, Task } from '../types'
import { ChainStateTag } from './Inventory'

interface Overview {
  bikes: Bike[]
  queue: Task[]
  chains: ChainRow[]
  brakes: BrakeRow[]
  recent_rides: RideRow[]
  flagged_rides: RideRow[]
  flagged_count: number
  safety_note: string
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>('/overview')
  if (loading && !data) return <Loading what="Loading overview" />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  if (!data.bikes.length)
    return (
      <Empty title="Welcome to Bike Log">
        Start with a bike: <Link to="/bikes">add your first bike</Link>, then add components with just a type and a name. Details can come later.
      </Empty>
    )
  const spare = data.chains.filter((c) => c.location.state !== 'INSTALLED' && c.state !== 'RETIRED')
  return (
    <div className="grid">
      <Card title="What needs attention" className="span-2">
        <TaskList tasks={data.queue} onChange={reload} />
        <p className="footnote">{data.safety_note}</p>
      </Card>
      <Card title="Bikes">
        <ul className="list">
          {data.bikes.map((b) => (
            <li key={b.id}>
              <Link to={`/bikes/${b.id}`}>{b.name}</Link>
              <span title={certaintyLabel(b.usage)}>{usageText(b.usage)}</span>
              {b.open_tasks > 0 && <Tag tone="warn">{b.open_tasks} due</Tag>}
              {b.status === 'RETIRED' && <Tag>retired</Tag>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Chains" actions={<Link to="/inventory?tab=chains">All chains</Link>}>
        {data.chains.length === 0 ? (
          <Empty title="No chains yet" />
        ) : (
          <ul className="list">
            {data.chains.map((c) => (
              <li key={c.component_id}>
                <Link to={`/inventory/${c.component_id}`}>{c.label}</Link>
                <ChainStateTag state={c.state} />
                <span className="muted small">{c.text}</span>
              </li>
            ))}
          </ul>
        )}
        {spare.some((c) => c.state === 'READY_TO_INSTALL') && <p className="small">Ready to install: {spare.filter((c) => c.state === 'READY_TO_INSTALL').map((c) => c.label).join(', ')}</p>}
      </Card>
      <Card title="Brakes">
        {data.brakes.length === 0 ? (
          <Empty title="No brake circuits tracked">Add front and rear brake circuits under Inventory to get fluid reminders.</Empty>
        ) : (
          <ul className="list">
            {data.brakes.map((b) => (
              <li key={b.component_id}>
                <Link to={`/inventory/${b.component_id}`}>{b.label}</Link>
                {b.fluid && <StatusBadge status={b.fluid.status} />}
                <span className="muted small">{b.fluid?.explanation}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Recent rides" actions={<Link to="/rides">All rides</Link>}>
        {data.recent_rides.length === 0 ? (
          <Empty title="No rides yet">Add a ride (bike, date and distance are enough) or import a CSV in Settings.</Empty>
        ) : (
          <ul className="list">
            {data.recent_rides.map((r) => (
              <li key={r.id} className={r.inclusion === 'EXCLUDED' ? 'excluded' : ''}>
                <span>{when(r.start_time_utc ?? r.ride_date)}</span>
                <Link to={`/rides?open=${r.id}`}>{r.name || 'Ride'}</Link>
                <span>{km(r.distance_km)}</span>
                {r.flags.length > 0 && <Tag tone="warn">{r.flags.length} flag{r.flags.length > 1 ? 's' : ''}</Tag>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {data.flagged_count > 0 && (
        <Card title={`Rides to review (${data.flagged_count})`}>
          <ul className="list">
            {data.flagged_rides.slice(0, 6).map((r) => (
              <li key={r.id}>
                <Link to={`/rides?open=${r.id}`}>{r.name || when(r.ride_date)}</Link>
                <span className="muted small">{r.flags[0].detail}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
