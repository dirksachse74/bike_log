import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, newOpId } from '../api'
import LogMaintenance from '../components/LogMaintenance'
import TaskList from '../components/TaskList'
import { Card, ChangeNotice, Empty, ErrorBox, Field, FormError, Loading, Sheet, StatusBadge, Tag } from '../components/ui'
import { useApp } from '../context'
import { certaintyLabel, km, slotName, today, usageText, when } from '../format'
import { useApi } from '../hooks'
import type { Bike, BrakeRow, Change, ComponentSummary, EventRow, OpResult, RideRow, SetupRow, Task } from '../types'

export function BikeForm({ onSaved }: { onSaved: (b: Bike) => void }) {
  const [f, setF] = useState({ name: '', maker: '', model: '', strava_gear_id: '', starting_km: '', starting_date: today(), starting_is_estimate: true })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  async function save() {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { name: f.name }
      if (f.maker) body.maker = f.maker
      if (f.model) body.model = f.model
      if (f.strava_gear_id) body.strava_gear_id = f.strava_gear_id
      if (f.starting_km) Object.assign(body, { starting_km: Number(f.starting_km), starting_date: f.starting_date, starting_is_estimate: f.starting_is_estimate })
      onSaved(await api.post<Bike>('/bikes', body, opId))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="form">
      <Field label="Name">
        <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="TIME NXR" autoFocus />
      </Field>
      <div className="row">
        <Field label="Maker (optional)">
          <input value={f.maker} onChange={(e) => setF({ ...f, maker: e.target.value })} />
        </Field>
        <Field label="Model (optional)">
          <input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} />
        </Field>
      </div>
      <Field label="Odometer when you start tracking (optional)" hint="Leave empty if unknown. Rides before this date are inside this value.">
        <div className="row">
          <input inputMode="decimal" value={f.starting_km} onChange={(e) => setF({ ...f, starting_km: e.target.value })} placeholder="km" />
          <input type="date" value={f.starting_date} onChange={(e) => setF({ ...f, starting_date: e.target.value })} />
        </div>
      </Field>
      <label className="check">
        <input type="checkbox" checked={f.starting_is_estimate} onChange={(e) => setF({ ...f, starting_is_estimate: e.target.checked })} /> The odometer value is an estimate
      </label>
      <Field label="Strava gear id (optional)" hint="Only used to match imported rides to this bike.">
        <input value={f.strava_gear_id} onChange={(e) => setF({ ...f, strava_gear_id: e.target.value })} placeholder="13071041" />
      </Field>
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !f.name.trim()} onClick={save}>
          {busy ? 'Saving…' : 'Add bike'}
        </button>
      </div>
    </div>
  )
}

export function BikesPage() {
  const { data, error, loading, reload } = useApi<Bike[]>('/bikes')
  const [adding, setAdding] = useState(false)
  const nav = useNavigate()
  return (
    <Card title="Bikes" actions={<button className="btn btn-primary" onClick={() => setAdding(true)}>Add bike</button>}>
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && data.length === 0 && <Empty title="No bikes yet">Add a bike to start logging rides and parts.</Empty>}
      {data && data.length > 0 && (
        <div className="cards">
          {data.map((b) => (
            <Link key={b.id} to={`/bikes/${b.id}`} className="tile">
              <strong>{b.name}</strong>
              <span title={certaintyLabel(b.usage)}>{usageText(b.usage)}</span>
              <span className="muted small">
                {b.usage.ride_count} rides · {certaintyLabel(b.usage)}
              </span>
              {b.open_tasks > 0 && <Tag tone="warn">{b.open_tasks} due</Tag>}
              {b.status === 'RETIRED' && <Tag>retired</Tag>}
            </Link>
          ))}
        </div>
      )}
      {adding && (
        <Sheet title="Add bike" onClose={() => setAdding(false)}>
          <BikeForm onSaved={(b) => nav(`/bikes/${b.id}`)} />
        </Sheet>
      )}
    </Card>
  )
}

interface BikeDetail extends Bike {
  setup: SetupRow[]
  history: { id: number; component_id: number; label: string; slot: string; installed_at: string; removed_at: string | null; removal_reason: string | null; voided: boolean }[]
  queue: Task[]
  brakes: BrakeRow[]
  rides: RideRow[]
  events: EventRow[]
}

export function InstallForm({ bikeId, onDone }: { bikeId: number; onDone: (c: Change) => void }) {
  const { meta } = useApp()
  const stored = useApi<ComponentSummary[]>('/components?state=STORED')
  const setupQ = useApi<BikeDetail>(`/bikes/${bikeId}`)
  const [f, setF] = useState({ component_id: '', slot: '', parent_component_id: '', at: today(), until: '' })
  const [preview, setPreview] = useState<Change | null>(null)
  const [error, setError] = useState<string | null>(null)
  const comp = stored.data?.find((c) => String(c.id) === f.component_id)
  const ctype = meta.component_types.find((t) => t.code === comp?.component_type)
  const parents = (setupQ.data?.setup ?? []).filter((s) => ctype?.parent_types.includes(s.component_type))
  const needsParent = ['TIRE', 'BRAKE_ROTOR'].includes(ctype?.code ?? '')
  const body = () => {
    const b: Record<string, unknown> = { at: f.at }
    if (f.parent_component_id) b.parent_component_id = Number(f.parent_component_id)
    else b.bike_id = bikeId
    if (f.slot) b.slot = f.slot
    if (f.until) b.until = f.until
    return b
  }
  async function run(dry: boolean) {
    setError(null)
    try {
      const r = await api.post<OpResult<unknown>>(`/components/${f.component_id}/install${dry ? '?dry_run=true' : ''}`, body())
      if (dry) setPreview(r.change)
      else onDone(r.change)
    } catch (e) {
      setError((e as Error).message)
      setPreview(null)
    }
  }
  if (stored.loading) return <Loading />
  if (!stored.data?.length) return <Empty title="No parts in storage">Add a part under Inventory first, or use Replace on an installed part.</Empty>
  return (
    <div className="form">
      <Field label="Part from storage">
        <select value={f.component_id} onChange={(e) => setF({ ...f, component_id: e.target.value, slot: '', parent_component_id: '' })}>
          <option value="">Pick a part…</option>
          {stored.data.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label} ({c.type_name}, {usageText(c.usage)})
            </option>
          ))}
        </select>
      </Field>
      {ctype && ctype.parent_types.length > 0 && (
        <Field label="Mount on" hint="Tires and rotors go on a wheel; the cassette can go on the rear wheel.">
          <select value={f.parent_component_id} onChange={(e) => setF({ ...f, parent_component_id: e.target.value })}>
            {needsParent ? <option value="">Pick a wheel…</option> : <option value="">the bike itself</option>}
            {parents.map((p) => (
              <option key={p.component_id} value={p.component_id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
      )}
      {ctype && ctype.slots.length > 1 && !f.parent_component_id && (
        <Field label="Position">
          <select value={f.slot} onChange={(e) => setF({ ...f, slot: e.target.value })}>
            <option value="">Pick…</option>
            {ctype.slots.map((s) => (
              <option key={s} value={s}>
                {slotName(s)}
              </option>
            ))}
          </select>
        </Field>
      )}
      {ctype && ctype.slots.length === 0 && (
        <Field label="Slot name">
          <input value={f.slot} onChange={(e) => setF({ ...f, slot: e.target.value.toUpperCase().replace(/\s+/g, '_') })} placeholder="e.g. BOTTLE_CAGE_1" />
        </Field>
      )}
      <div className="row">
        <Field label="Installed on" hint="Effective date; history before today is fine.">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
        <Field label="Removed on (only for past periods)">
          <input type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} />
        </Field>
      </div>
      <ChangeNotice change={preview} />
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn" disabled={!f.component_id} onClick={() => run(true)}>
          Preview mileage impact
        </button>
        <button className="btn btn-primary" disabled={!f.component_id} onClick={() => run(false)}>
          Install
        </button>
      </div>
    </div>
  )
}

function PartActions({ row, onDone }: { row: SetupRow; onDone: (c: Change) => void }) {
  const stored = useApi<ComponentSummary[]>(`/components?state=STORED&component_type=${row.component_type}`)
  const [mode, setMode] = useState<'remove' | 'replace'>('replace')
  const [f, setF] = useState({ at: today(), reason: '', new_component_id: 'same' })
  const [preview, setPreview] = useState<Change | null>(null)
  const [error, setError] = useState<string | null>(null)
  async function run(dry: boolean) {
    setError(null)
    try {
      const q = dry ? '?dry_run=true' : ''
      const r =
        mode === 'remove'
          ? await api.post<OpResult<unknown>>(`/components/${row.component_id}/remove${q}`, { at: f.at, reason: f.reason || null })
          : await api.post<OpResult<unknown>>(`/components/${row.component_id}/replace${q}`, {
              at: f.at,
              reason: f.reason || 'replaced',
              ...(f.new_component_id === 'same' ? { same_product: true } : { new_component_id: Number(f.new_component_id) }),
            })
      if (dry) setPreview(r.change)
      else onDone(r.change)
    } catch (e) {
      setError((e as Error).message)
      setPreview(null)
    }
  }
  return (
    <div className="form">
      <div className="chips">
        <button className={`chip ${mode === 'replace' ? 'chip-on' : ''}`} onClick={() => setMode('replace')}>
          Replace / swap
        </button>
        <button className={`chip ${mode === 'remove' ? 'chip-on' : ''}`} onClick={() => setMode('remove')}>
          Remove to storage
        </button>
      </div>
      {mode === 'replace' && (
        <Field label="New part" hint="Swapping chains? Pick the spare. 'Same product' creates a new part with the same product model.">
          <select value={f.new_component_id} onChange={(e) => setF({ ...f, new_component_id: e.target.value })}>
            <option value="same">New part, same product</option>
            {stored.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label} ({usageText(c.usage)})
              </option>
            ))}
          </select>
        </Field>
      )}
      <div className="row">
        <Field label="Effective date">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
        <Field label="Reason (optional)">
          <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="rotation, worn, crash…" />
        </Field>
      </div>
      <p className="muted small">This is a real change of parts. If the record itself is wrong, open the part and correct its installation instead.</p>
      <ChangeNotice change={preview} />
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn" onClick={() => run(true)}>
          Preview mileage impact
        </button>
        <button className="btn btn-primary" onClick={() => run(false)}>
          {mode === 'remove' ? 'Remove' : 'Replace'}
        </button>
      </div>
    </div>
  )
}

export function BikeDetailPage() {
  const { id } = useParams()
  const { toast } = useApp()
  const { data, error, loading, reload } = useApi<BikeDetail>(`/bikes/${id}`)
  const [sheet, setSheet] = useState<null | { kind: 'install' } | { kind: 'part'; row: SetupRow } | { kind: 'log' }>(null)
  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const done = (c: Change) => {
    setSheet(null)
    toast(c.notice)
    reload()
  }
  return (
    <div className="grid">
      <Card
        title={data.name}
        className="span-2"
        actions={
          <>
            <button className="btn btn-primary" onClick={() => setSheet({ kind: 'log' })}>
              Log maintenance
            </button>
            <button className="btn" onClick={() => setSheet({ kind: 'install' })}>
              Install part
            </button>
          </>
        }
      >
        <div className="stats">
          <div>
            <span className="stat">{usageText(data.usage)}</span>
            <span className="muted small">{certaintyLabel(data.usage)}</span>
          </div>
          <div>
            <span className="stat">{data.usage.ride_count}</span>
            <span className="muted small">rides</span>
          </div>
          <div>
            <span className="stat">{data.usage.hours.toFixed(0)} h</span>
            <span className="muted small">ride time</span>
          </div>
        </div>
        {data.usage.starting_km !== null && (
          <p className="small muted">
            Odometer {data.usage.starting_is_estimate ? '≈' : ''}
            {km(data.usage.starting_km, 0)} as of {when(data.usage.starting_effective)}
            {data.usage.starting_is_estimate ? ' (estimate)' : ''}, plus {km(data.usage.ride_km)} from rides since.
          </p>
        )}
      </Card>
      <Card title="Installed now">
        {data.setup.length === 0 ? (
          <Empty title="Nothing installed yet">Install parts to track their usage.</Empty>
        ) : (
          <ul className="list setup">
            {data.setup.map((s) => (
              <li key={s.installation_id} style={{ paddingLeft: `${s.depth * 1.2}rem` }}>
                <span className="muted small">{slotName(s.slot)}</span>
                <Link to={`/inventory/${s.component_id}`}>{s.label}</Link>
                <span className="muted small">since {when(s.since)}</span>
                <button className="btn btn-small" onClick={() => setSheet({ kind: 'part', row: s })}>
                  Change
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Service status">
        <TaskList tasks={data.queue} onChange={reload} emptyText="No rules apply to the installed parts yet." />
      </Card>
      {data.brakes.length > 0 && (
        <Card title="Brake circuits">
          <ul className="list">
            {data.brakes.map((b) => (
              <li key={b.component_id}>
                <strong>{b.position}</strong>
                <Link to={`/inventory/${b.component_id}`}>{b.label}</Link>
                {b.fluid && <StatusBadge status={b.fluid.status} />}
                <span className="small muted">{b.last_bleed ? `Last bleed ${when(b.last_bleed.date)}: ${b.last_bleed.symptom ?? ''} → ${b.last_bleed.outcome ?? '?'}` : 'No bleed recorded'}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="Recent maintenance">
        {data.events.length === 0 ? (
          <Empty title="No maintenance logged" />
        ) : (
          <ul className="list">
            {data.events.map((e) => (
              <li key={e.id} className={e.voided ? 'excluded' : ''}>
                <span>{when(e.performed_at)}</span>
                <span>{e.action}</span>
                <span className="muted">{e.component}</span>
                {e.outcome && <Tag>{e.outcome.toLowerCase()}</Tag>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Installation history" className="span-2">
        <table className="table">
          <thead>
            <tr>
              <th>Part</th>
              <th>Slot</th>
              <th>From</th>
              <th>Until</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {data.history.map((h) => (
              <tr key={h.id} className={h.voided ? 'excluded' : ''}>
                <td>
                  <Link to={`/inventory/${h.component_id}`}>{h.label}</Link>
                </td>
                <td>{slotName(h.slot)}</td>
                <td>{when(h.installed_at)}</td>
                <td>{h.removed_at ? when(h.removed_at) : 'now'}</td>
                <td>{h.voided ? 'corrected (void)' : h.removal_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {sheet?.kind === 'install' && (
        <Sheet title="Install a part" onClose={() => setSheet(null)}>
          <InstallForm bikeId={data.id} onDone={done} />
        </Sheet>
      )}
      {sheet?.kind === 'part' && (
        <Sheet title={`Change ${sheet.row.label}`} onClose={() => setSheet(null)}>
          <PartActions row={sheet.row} onDone={done} />
        </Sheet>
      )}
      {sheet?.kind === 'log' && (
        <Sheet title={`Log maintenance · ${data.name}`} onClose={() => setSheet(null)}>
          <LogMaintenance
            bikeId={data.id}
            onDone={(msg) => {
              setSheet(null)
              toast(msg)
              reload()
            }}
          />
        </Sheet>
      )}
    </div>
  )
}
