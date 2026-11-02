import { useState } from 'react'
import { Link } from 'react-router-dom'
import EventLog from '../components/EventLog'
import LogMaintenance from '../components/LogMaintenance'
import { GroupedTasks } from '../components/TaskList'
import { Card, Empty, ErrorBox, Loading, Sheet } from '../components/ui'
import { useApp } from '../context'
import { useApi } from '../hooks'
import type { Bike, EventRow, Task } from '../types'

export default function MaintenancePage() {
  const { toast, meta } = useApp()
  const [bike, setBike] = useState('')
  const [all, setAll] = useState(false)
  const bikes = useApi<Bike[]>('/bikes')
  const q = useApi<Task[]>(`/maintenance/queue?include_ok=${all}${bike ? `&bike_id=${bike}` : ''}`)
  const events = useApi<EventRow[]>(`/maintenance/events?limit=50${bike ? `&bike_id=${bike}` : ''}`)
  const [logging, setLogging] = useState(false)
  const refresh = () => {
    q.reload()
    events.reload()
  }
  return (
    <div className="grid">
      <Card
        title="Maintenance"
        className="span-2"
        actions={
          <button className="btn btn-primary" onClick={() => setLogging(true)} title="Cleaning, lubing, waxing, charging, checks, bleeds, repairs: anything you did to the bike or a part">
            Record work done
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
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Also list reminders that are up to date
          </label>
        </div>
        {q.loading && !q.data && <Loading />}
        {q.error && <ErrorBox error={q.error} onRetry={q.reload} />}
        {q.data && (q.data.length ? <GroupedTasks tasks={q.data} onChange={refresh} /> : <Empty title="Nothing due by recorded usage.">{meta.safety_note}</Empty>)}
        <p className="footnote">{meta.safety_note}</p>
      </Card>
      <Card title="Recently logged">
        {events.loading && !events.data && <Loading />}
        {events.error && <ErrorBox error={events.error} onRetry={events.reload} />}
        {events.data?.length === 0 && <Empty title="Nothing logged yet">Use “Record work done”: pick the bike, tap what you did, and the installed parts are preselected.</Empty>}
        {events.data && events.data.length > 0 && <EventLog events={events.data} onChanged={refresh} show="both" />}
      </Card>
      <Card title="Service intervals">
        <p className="small">
          How long hot wax, liquid wax, a charge, brake fluid and every other check last: <Link to="/settings?section=intervals">Settings → Service intervals</Link>.
        </p>
      </Card>
      {logging && (
        <Sheet title="Record work done" onClose={() => setLogging(false)}>
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
