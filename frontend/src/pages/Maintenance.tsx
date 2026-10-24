import { useState } from 'react'
import { Link } from 'react-router-dom'
import LogMaintenance from '../components/LogMaintenance'
import TaskList from '../components/TaskList'
import { Card, Empty, ErrorBox, Loading, Sheet, Tag } from '../components/ui'
import { useApp } from '../context'
import { when } from '../format'
import { useApi } from '../hooks'
import type { Bike, EventRow, Rule, Task } from '../types'

export default function MaintenancePage() {
  const { toast, meta } = useApp()
  const [bike, setBike] = useState('')
  const [all, setAll] = useState(false)
  const bikes = useApi<Bike[]>('/bikes')
  const q = useApi<Task[]>(`/maintenance/queue?include_ok=${all}${bike ? `&bike_id=${bike}` : ''}`)
  const events = useApi<EventRow[]>(`/maintenance/events?limit=50${bike ? `&bike_id=${bike}` : ''}`)
  const rules = useApi<Rule[]>('/rules')
  const [logging, setLogging] = useState(false)
  const refresh = () => {
    q.reload()
    events.reload()
  }
  const typeName = (c: string | null) => meta.component_types.find((t) => t.code === c)?.name ?? c
  return (
    <div className="grid">
      <Card
        title="Maintenance"
        className="span-2"
        actions={
          <button className="btn btn-primary" onClick={() => setLogging(true)}>
            Log maintenance
          </button>
        }
      >
        <div className="filters">
          <select value={bike} onChange={(e) => setBike(e.target.value)} aria-label="Bike">
            <option value="">All bikes</option>
            {bikes.data?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
          <label className="check">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show items that are OK
          </label>
        </div>
        {q.loading && !q.data && <Loading />}
        {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
        {q.data && <TaskList tasks={q.data} onChange={refresh} />}
        <p className="footnote">{meta.safety_note}</p>
      </Card>
      <Card title="Recently logged">
        {events.loading && !events.data && <Loading />}
        {events.error && <ErrorBox error={events.error} onRetry={events.reload} />}
        {events.data?.length === 0 && <Empty title="Nothing logged yet">Use “Log maintenance”: pick the bike, tap what you did, and the installed parts are preselected.</Empty>}
        <ul className="list">
          {events.data?.map((e) => (
            <li key={e.id} className={e.voided ? 'excluded' : ''}>
              <span>{when(e.performed_at)}</span>
              <strong>{e.action}</strong>
              {e.component_id ? <Link to={`/inventory/${e.component_id}`}>{e.component}</Link> : <span>{e.bike}</span>}
              {e.outcome && <Tag>{e.outcome.toLowerCase()}</Tag>}
              {e.voided && <Tag>void</Tag>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Default intervals">
        {rules.loading && !rules.data && <Loading />}
        <ul className="list">
          {rules.data?.map((r) => (
            <li key={r.id}>
              <span>
                {typeName(r.component_type)}: {r.name}
              </span>
              <span className="muted small">
                {r.trigger === 'CYCLE_WINDOW' ? `once at ${r.window_min_km}–${r.window_max_km} km per hot-wax cycle` : [r.interval_km && `${r.interval_km} km`, r.interval_months && `${r.interval_months} months`].filter(Boolean).join(' or ')}
                {' · '}
                {r.origin.toLowerCase()}
              </span>
            </li>
          ))}
        </ul>
        <p className="small muted">Change an interval from any part's page (for that part or for all parts of its type).</p>
      </Card>
      {logging && (
        <Sheet title="Log maintenance" onClose={() => setLogging(false)}>
          <LogMaintenance
            bikeId={bike ? Number(bike) : null}
            onDone={(msg) => {
              setLogging(false)
              toast(msg)
              refresh()
            }}
          />
        </Sheet>
      )}
    </div>
  )
}
