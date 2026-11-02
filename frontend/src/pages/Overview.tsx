import { Link } from 'react-router-dom'
import { Card, Empty, ErrorBox, Loading, StatusBadge, Tag } from '../components/ui'
import { IncidentRows } from '../components/Incidents'
import { GroupedTasks } from '../components/TaskList'
import { certaintyLabel, km, usageText, when } from '../format'
import { useApi } from '../hooks'
import type { Bike, BrakeRow, ChainRow, RideIncident, RideRow, ShoppingItem, SpareCheck, Task } from '../types'
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
  shopping_list: ShoppingItem[]
  spares: SpareCheck[]
  open_incidents: RideIncident[]
}

// Upcoming tasks: what is due now stays open; coming soon, snoozed and "needs a first entry" fold away.
function UpcomingTasks({ tasks, incidents, note, reload }: { tasks: Task[]; incidents: RideIncident[]; note: string; reload: () => void }) {
  return (
    <Card title="Upcoming tasks" className="span-2">
      <GroupedTasks
        tasks={tasks}
        onChange={reload}
        foldSoon
        nothingDue={incidents.length === 0 ? 'Nothing due right now.' : null}
        before={
          incidents.length > 0 && (
            <div className="open-incidents">
              <h3 className="small muted">Open incidents</h3>
              <IncidentRows incidents={incidents} bikeName={null} showRide showBike onChanged={reload} />
            </div>
          )
        }
      />
      <p className="footnote">{note}</p>
    </Card>
  )
}

// One tile per bike at the top: name, km and how many reminders are due, one tap to the bike.
function BikeStrip({ bikes }: { bikes: Bike[] }) {
  return (
    <div className="bike-strip span-2" aria-label="Bikes">
      {bikes.map((b) => (
        <Link key={b.id} to={`/bikes/${b.id}`} className="tile tile-small">
          <strong>{b.name}</strong>
          <span title={certaintyLabel(b.usage)}>{usageText(b.usage)}</span>
          <span>
            {b.open_tasks > 0 ? <Tag tone="warn">{b.open_tasks} due</Tag> : <span className="muted small">nothing due</span>}
            {b.status === 'RETIRED' && <Tag>retired</Tag>}
          </span>
        </Link>
      ))}
    </div>
  )
}

function ShoppingCard({ items, spares }: { items: ShoppingItem[]; spares: SpareCheck[] }) {
  return (
    <Card title="Shopping list" actions={<Link to="/inventory?tab=shopping">Inventory</Link>}>
      {items.length === 0 ? (
        <p className="small muted">Nothing to buy: stock and spares are above their minimum.</p>
      ) : (
        <ul className="list">
          {items.map((s) => (
            <li key={s.consumable_id ?? s.component_type}>
              <strong>{s.name}</strong>
              <span className="small">
                buy {s.suggested_qty} · {s.available} at home, keep {s.min_stock}
              </span>
            </li>
          ))}
        </ul>
      )}
      {spares.length > 0 && (
        <details className="task-group" data-group="spares">
          <summary>
            <strong>Spares at home</strong> <span className="muted small">{spares.map((r) => `${r.have} ${r.unit}${r.have === 1 ? '' : 's'}`).join(' · ')}</span>
          </summary>
          <ul className="list">
            {spares.map((r) => (
              <li key={r.component_type}>
                <span>{r.type_name}</span>
                <span className="small">{r.text}</span>
                {r.low && <Tag tone="warn">low</Tag>}
              </li>
            ))}
          </ul>
          <p className="small muted">Change how many to keep under Settings → Spares to keep.</p>
        </details>
      )}
    </Card>
  )
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
      <BikeStrip bikes={data.bikes} />
      <UpcomingTasks tasks={data.queue} incidents={data.open_incidents} note={data.safety_note} reload={reload} />
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
      <Card title="Recent rides" actions={<Link to="/rides">All rides</Link>}>
        {data.recent_rides.length === 0 ? (
          <Empty title="No rides yet">Add a ride (bike, date and distance are enough) or import a CSV in Settings.</Empty>
        ) : (
          <details className="task-group" data-group="rides">
          <summary>
            <strong>{data.recent_rides[0].name || 'Ride'}</strong>{' '}
            <span className="muted small">
              {when(data.recent_rides[0].start_time_utc ?? data.recent_rides[0].ride_date)} · {km(data.recent_rides[0].distance_km)} · {data.recent_rides.length} recent ride{data.recent_rides.length === 1 ? '' : 's'}
            </span>
          </summary>
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
          </details>
        )}
      </Card>
      <ShoppingCard items={data.shopping_list} spares={data.spares} />
      <Card title="Chains" actions={<Link to="/inventory?tab=chains">All chains</Link>}>
        {data.chains.length === 0 ? (
          <Empty title="No chains yet" />
        ) : (
          <details className="task-group" data-group="chains">
          <summary>
            <strong>{data.chains.length} chain{data.chains.length === 1 ? '' : 's'}</strong>{' '}
            <span className="muted small">{spare.filter((c) => c.state === 'READY_TO_INSTALL').length} ready to install</span>
          </summary>
          <ul className="list">
            {data.chains.map((c) => (
              <li key={c.component_id}>
                <Link to={`/inventory/${c.component_id}`}>{c.label}</Link>
                {c.mark && <span className="mark">{c.mark}</span>}
                <ChainStateTag state={c.state} />
                <span className="muted small">{c.text}</span>
              </li>
            ))}
          </ul>
          </details>
        )}
        {spare.some((c) => c.state === 'READY_TO_INSTALL') && <p className="small">Ready to install: {spare.filter((c) => c.state === 'READY_TO_INSTALL').map((c) => c.label).join(', ')}</p>}
      </Card>
      <Card title="Brakes">
        {data.brakes.length === 0 ? (
          <Empty title="No brake circuits tracked">Add front and rear brake circuits under Inventory to get fluid reminders.</Empty>
        ) : (
          <details className="task-group" data-group="brakes">
          <summary>
            <strong>{data.brakes.length} brake circuit{data.brakes.length === 1 ? '' : 's'}</strong>{' '}
            <span className="muted small">{data.brakes.some((b) => b.fluid && ['OVERDUE', 'DUE', 'DUE_SOON'].includes(b.fluid.status)) ? 'fluid due soon' : 'fluid OK or not recorded'}</span>
          </summary>
          <ul className="list">
            {data.brakes.map((b) => (
              <li key={b.component_id}>
                <Link to={`/inventory/${b.component_id}`}>{b.label}</Link>
                {b.fluid && <StatusBadge status={b.fluid.status} />}
                <span className="muted small">{b.fluid?.explanation}</span>
              </li>
            ))}
          </ul>
          </details>
        )}
      </Card>
    </div>
  )
}
