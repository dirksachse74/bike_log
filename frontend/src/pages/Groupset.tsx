// The groupset of a bike as one thing: the parts in its groupset positions now (drivetrain, shifting, brakes,
// the Di2 / AXS battery, plus the cassette and rotors on the wheels). Combined km, service tasks, incidents,
// maintenance log and journal; the parts unfold to their own parts, each linking to its page.
import { Link, useParams } from 'react-router-dom'
import { IncidentRows } from '../components/Incidents'
import PartTree from '../components/PartTree'
import TaskList from '../components/TaskList'
import { Card, Empty, ErrorBox, Loading, Tag } from '../components/ui'
import { km, when } from '../format'
import { useApi } from '../hooks'
import type { GroupsetPageData } from '../types'

export function GroupsetPage() {
  const { id } = useParams()
  const { data, error, loading, reload } = useApi<GroupsetPageData>(`/bikes/${id}/groupset`)
  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const back = <Link to={`/bikes/${data.bike_id}`}>{data.bike}</Link>
  if (!data.parts.length)
    return (
      <Card title="Groupset" className="span-2">
        <Empty title="No groupset parts on this bike">Add them on {back} → Manage parts → Add groupset.</Empty>
      </Card>
    )
  const open = data.tasks.filter((t) => !['OK', 'SNOOZED', 'INSUFFICIENT_INFO'].includes(t.status))
  const rest = data.tasks.filter((t) => !open.includes(t))
  return (
    <div className="grid">
      <Card title={data.name} className="span-2">
        <p className="small muted">
          Groupset on {back}
          {data.since ? `, parts on it since ${when(data.since)}` : ''}. It is the parts in the groupset positions now: a part you swap in
          joins it, a part you take off leaves it.
        </p>
        <div className="stats">
          <div>
            <span className="stat">{km(data.stats.km, 0)}</span>
            <span className="muted small">on this bike since then</span>
          </div>
          <div>
            <span className="stat">{data.stats.hours.toFixed(0)} h</span>
            <span className="muted small">ride time{data.stats.rides_without_time ? ` (${data.stats.rides_without_time} rides without time)` : ''}</span>
          </div>
          <div>
            <span className="stat">{data.stats.parts}</span>
            <span className="muted small">parts</span>
          </div>
          <div>
            <span className="stat">{data.stats.due}</span>
            <span className="muted small">need attention</span>
          </div>
        </div>
        <p className="small muted">Each part keeps its own km (a chain swapped in later has fewer); open a part for its own numbers.</p>
      </Card>
      <Card title="Parts" className="span-2">
        <details className="task-group" data-group="groupset-parts">
          <summary>
            <strong>Show the {data.stats.parts} parts</strong>
            <span className="muted small">{data.parts.map((n) => n.label).slice(0, 3).join(', ')}, …</span>
          </summary>
          <PartTree nodes={data.parts} />
        </details>
      </Card>
      <Card title="Service tasks" className="span-2">
        <TaskList tasks={open} onChange={reload} emptyText="Nothing due on the groupset." />
        {rest.length > 0 && (
          <details className="task-group">
            <summary>
              <strong>Up to date, snoozed or needing a first entry</strong>
              <span className="muted small">{rest.length}</span>
            </summary>
            <TaskList tasks={rest} onChange={reload} />
          </details>
        )}
      </Card>
      <Card title="Incidents" className="span-2">
        {data.incidents.length ? (
          <IncidentRows incidents={data.incidents} bikeName={data.bike} showRide onChanged={reload} />
        ) : (
          <Empty title="No incidents on the groupset parts" />
        )}
      </Card>
      <Card title="Maintenance log">
        {data.events.length === 0 ? (
          <Empty title="Nothing logged yet" />
        ) : (
          <ul className="list">
            {data.events.slice(0, 50).map((e) => (
              <li key={e.id} className={e.voided ? 'excluded' : ''}>
                <span>{when(e.performed_at)}</span>
                <span>{e.action}</span>
                {e.component_id && <Link to={`/inventory/${e.component_id}`}>{e.component}</Link>}
                {e.outcome && <Tag>{e.outcome.toLowerCase()}</Tag>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Journal">
        {data.journal.length === 0 ? (
          <Empty title="No notes yet">Add a note on a part's page.</Empty>
        ) : (
          <ul className="list">
            {data.journal.map((j) => (
              <li key={j.id}>
                <span>{when(j.on)}</span>
                {j.kind === 'ISSUE' && <Tag tone={j.open_issue ? 'warn' : 'neutral'}>{j.open_issue ? 'open issue' : 'issue solved'}</Tag>}
                <span>{j.text}</span>
                {j.component_id && <Link to={`/inventory/${j.component_id}`}>{j.component_label}</Link>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
