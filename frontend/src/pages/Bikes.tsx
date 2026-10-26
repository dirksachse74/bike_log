import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, newOpId } from '../api'
import Bundles from '../components/Bundles'
import { BikeIncidents } from '../components/Incidents'
import GroupsetImport from '../components/GroupsetImport'
import ChangeLog from '../components/ChangeLog'
import Journal from '../components/Journal'
import LogMaintenance from '../components/LogMaintenance'
import { MoveForm, RemoveForm, ReplaceForm } from '../components/PartChange'
import { SwapTube } from '../components/Repairs'
import MountPicker, { type MountTarget } from '../components/MountPicker'
import ChainRotation from '../components/ChainRotation'
import { AwayCard } from '../components/ServiceOrders'
import TaskList from '../components/TaskList'
import { PressureNote, TireSetupSelect } from '../components/TireSetup'
import { Card, ChangeNotice, Empty, ErrorBox, Field, FormError, Loading, Sheet, StatusBadge, Tag } from '../components/ui'
import { useApp } from '../context'
import { centsInput, certaintyLabel, duration, euro, km, slotName, toCents, today, usageText, when } from '../format'
import { useApi } from '../hooks'
import { RideDetailView } from './Rides'
import type { Bike, BikeCosts, BrakeRow, Change, ComponentSummary, EventRow, GroupsetSummary, OpResult, RideIncident, RideRow, ServiceOrder, SetupRow, Task } from '../types'

export function BikeForm({ onSaved }: { onSaved: (b: Bike) => void }) {
  const { meta } = useApp()
  const [f, setF] = useState({ name: '', maker: '', model: '', strava_gear_id: '', starting_km: '', starting_date: today(), starting_is_estimate: true, price: '', purchase_date: '', shifting: '' })
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
      const price = toCents(f.price)
      if (Number.isNaN(price)) throw new Error('Price: enter an amount such as 3.499,00 or 3499')
      if (price !== null) body.purchase_price_cents = price
      if (f.purchase_date) body.purchase_date = f.purchase_date
      if (f.shifting) body.shifting = f.shifting
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
      <div className="row">
        <Field label="Purchase price (optional)" hint="Initial cost of the bike.">
          <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="€" />
        </Field>
        <Field label="Bought on (optional)">
          <input type="date" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} />
        </Field>
      </div>
      <Field label="Shifting" hint="Decides which reminders apply (Di2 checks or cable checks). Not set: electronic once a Di2/AXS battery is fitted.">
        <select aria-label="Shifting" value={f.shifting} onChange={(e) => setF({ ...f, shifting: e.target.value })}>
          <option value="">Not set</option>
          {meta.shifting_types.map((t) => (
            <option key={t.code} value={t.code}>
              {t.label}
            </option>
          ))}
        </select>
      </Field>
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
        <input value={f.strava_gear_id} onChange={(e) => setF({ ...f, strava_gear_id: e.target.value })} placeholder="90000001" />
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
          {data.filter((b) => b.status !== 'RETIRED').map((b) => (
            <Link key={b.id} to={`/bikes/${b.id}`} className="tile">
              <strong>{b.name}</strong>
              <span title={certaintyLabel(b.usage)}>{usageText(b.usage)}</span>
              <span className="muted small">
                {b.usage.ride_count} {b.usage.ride_count === 1 ? 'ride' : 'rides'} · {certaintyLabel(b.usage)}
              </span>
              <span className="small">
                Initial {b.costs.initial_known ? euro(b.costs.initial_cents) : 'not entered'} · running {b.costs.estimated ? '≈' : ''}
                {euro(b.costs.running_cents)}
              </span>
              {b.open_tasks > 0 && <Tag tone="warn">{b.open_tasks} due</Tag>}
            </Link>
          ))}
        </div>
      )}
      {data && data.some((b) => b.status === 'RETIRED') && (
        <details className="task-group" data-group="retired-bikes">
          <summary>
            <strong>Retired bikes</strong>
            <span className="muted small">{data.filter((b) => b.status === 'RETIRED').length}</span>
          </summary>
          <ul className="list">
            {data
              .filter((b) => b.status === 'RETIRED')
              .map((b) => (
                <li key={b.id}>
                  <Link to={`/bikes/${b.id}`}>{b.name}</Link>
                  <span className="muted small">
                    {usageText(b.usage)} · {b.usage.ride_count} {b.usage.ride_count === 1 ? 'ride' : 'rides'}
                  </span>
                </li>
              ))}
          </ul>
        </details>
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
  cost_detail: BikeCosts
  setup: SetupRow[]
  history_counts: { rides: number; installations: number; maintenance: number; journal: number; usage: number }
  history: { id: number; component_id: number; label: string; slot: string; installed_at: string; removed_at: string | null; removal_reason: string | null; voided: boolean }[]
  queue: Task[]
  brakes: BrakeRow[]
  rides: RideRow[]
  events: EventRow[]
  groupset: GroupsetSummary | null
  away: ServiceOrder[]
}

export function InstallForm({ bikeId, onDone }: { bikeId: number; onDone: (c: Change) => void }) {
  const { meta } = useApp()
  const stored = useApi<ComponentSummary[]>('/components?state=STORED')
  const [f, setF] = useState({ component_id: '', slot: '', at: today(), until: '' })
  const [mount, setMount] = useState<MountTarget | null>(null)
  const [preview, setPreview] = useState<Change | null>(null)
  const [error, setError] = useState<string | null>(null)
  const comp = stored.data?.find((c) => String(c.id) === f.component_id)
  const ctype = meta.component_types.find((t) => t.code === comp?.component_type)
  const body = () => {
    const b: Record<string, unknown> = { at: f.at }
    if (mount?.parent_component_id) b.parent_component_id = mount.parent_component_id
    else b.bike_id = bikeId
    const slot = mount?.slot ?? f.slot
    if (slot) b.slot = slot
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
        <select
          value={f.component_id}
          onChange={(e) => {
            setF({ ...f, component_id: e.target.value, slot: '' })
            setMount(null)
          }}
        >
          <option value="">Pick a part…</option>
          {stored.data.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label} ({c.type_name}, {usageText(c.usage)})
            </option>
          ))}
        </select>
      </Field>
      {ctype && <MountPicker key={ctype.code} componentType={ctype.code} bikeId={bikeId} value={mount} onChange={setMount} />}
      {mount && mount.slot === null && (
        <Field label="Position name">
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
        <button className="btn" disabled={!f.component_id || !mount} onClick={() => run(true)}>
          Preview mileage impact
        </button>
        <button className="btn btn-primary" disabled={!f.component_id || !mount} onClick={() => run(false)}>
          Install
        </button>
      </div>
    </div>
  )
}

function PartActions({ row, onDone }: { row: SetupRow; onDone: (c: Change) => void }) {
  const { meta } = useApp()
  const ctype = meta.component_types.find((t) => t.code === row.component_type)
  const canMove = !!ctype && (ctype.parent_types.length > 0 || ctype.slots.length > 1)
  const [mode, setMode] = useState<'replace' | 'remove' | 'move'>('replace')
  return (
    <div className="form">
      <div className="chips">
        <button className={`chip ${mode === 'replace' ? 'chip-on' : ''}`} onClick={() => setMode('replace')}>
          Replace
        </button>
        <button className={`chip ${mode === 'remove' ? 'chip-on' : ''}`} onClick={() => setMode('remove')}>
          Remove
        </button>
        {canMove && (
          <button className={`chip ${mode === 'move' ? 'chip-on' : ''}`} onClick={() => setMode('move')}>
            Move position
          </button>
        )}
      </div>
      {mode === 'replace' && <ReplaceForm componentId={row.component_id} onDone={(c) => onDone(c)} />}
      {mode === 'remove' && <RemoveForm componentId={row.component_id} suggested={ctype?.removed_default ?? 'STORED'} onDone={onDone} />}
      {mode === 'move' && <MoveForm componentId={row.component_id} onDone={onDone} />}
      <p className="muted small">This is a real change of parts. If the record itself is wrong, open the part and correct its installation instead.</p>
    </div>
  )
}

const BIKE_TABS: [string, string][] = [
  ['overview', 'Parts and service'],
  ['rides', 'Rides'],
  ['incidents', 'Incidents'],
  ['maintenance', 'Maintenance'],
  ['costs', 'Costs'],
  ['history', 'Journal and history'],
]

export function BikeDetailPage() {
  const { id } = useParams()
  const { toast } = useApp()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'overview'
  const { data, error, loading, reload } = useApi<BikeDetail>(`/bikes/${id}`)
  const incidents = useApi<RideIncident[]>(`/bikes/${id}/incidents`)
  const openIncidents = incidents.data?.filter((r) => r.open && !r.removed).length ?? 0
  const [sheet, setSheet] = useState<null | { kind: 'install' } | { kind: 'groupset'; replace?: boolean } | { kind: 'wheelset' } | { kind: 'costs' } | { kind: 'part'; row: SetupRow } | { kind: 'swap'; title: string; rows: SetupRow[]; remove?: boolean } | { kind: 'spokes'; row: SetupRow } | { kind: 'log' } | { kind: 'retire' }>(params.get('add') === 'groupset' ? { kind: 'groupset', replace: true } : null)
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
            {data.status === 'RETIRED' ? (
              <button
                className="btn btn-primary"
                onClick={async () => {
                  await api.post(`/bikes/${data.id}/restore`, {})
                  toast(`${data.name} is active again.`)
                  reload()
                }}
              >
                Restore bike
              </button>
            ) : (
              <button className="btn btn-primary" title="Cleaning, lubing, waxing, charging, checks, bleeds, repairs: anything you did to the bike or a part" onClick={() => setSheet({ kind: 'log' })}>
                Record work done
              </button>
            )}
            {data.status !== 'RETIRED' && (
              <button className="btn" onClick={() => setSheet({ kind: 'retire' })}>
                Retire or delete
              </button>
            )}
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
            <span className="muted small">
              {data.usage.ride_count === 1 ? 'ride' : 'rides'}
              {(data.usage.rides_before_start ?? 0) > 0 &&
                ` (+${data.usage.rides_before_start} before tracking, inside the starting km)`}
            </span>
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
        {data.status === 'RETIRED' && <p className="small"><Tag>retired</Tag> Hidden from the bike list; its rides, km and history are kept. Restore brings it back.</p>}
        <ShiftingSelect bike={data} onSaved={reload} />
      </Card>
      <div className="tabs span-2" role="tablist" aria-label="Bike sections">
        {BIKE_TABS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'tab-on' : ''}`} onClick={() => setParams(k === 'overview' ? {} : { tab: k })}>
            {l}
            {k === 'incidents' && openIncidents > 0 && <span className="count">{openIncidents}</span>}
          </button>
        ))}
      </div>
      {tab === 'overview' && (
        <>
          <AwayCard orders={data.away} onChanged={reload} />
          <ManageParts
            setup={data.setup}
            onSwap={(title, rows) => setSheet({ kind: 'swap', title, rows })}
            onInstall={() => setSheet({ kind: 'install' })}
            onRemove={(rows) => setSheet({ kind: 'swap', title: 'Remove a part', rows, remove: true })}
            onReplaceGroupset={() => setSheet({ kind: 'groupset', replace: true })}
            onWheelset={() => setSheet({ kind: 'wheelset' })}
          />
          <ChainRotation bikeId={data.id} refresh={data} onChanged={reload} />
          <Card
            title="Installed now"
            className="span-2"
            actions={
              // first setup of a bike: all parts of a groupset in one go; later changes are under Manage parts
              !data.groupset && (
                <button className="btn btn-small" title="Set up the bike: all parts of a groupset template in one go" onClick={() => setSheet({ kind: 'groupset' })}>
                  Add groupset
                </button>
              )
            }
          >
            {data.setup.length === 0 ? (
              <Empty title="Nothing installed yet">Tell the app what is on the bike: Add groupset puts a whole group on in one go; Manage parts → Install a part adds single parts.</Empty>
            ) : (
              <SetupGroups setup={data.setup} groupset={data.groupset} bikeId={data.id} onChange={(row) => setSheet({ kind: 'part', row })} reload={reload} onAddSpokes={(row) => setSheet({ kind: 'spokes', row })} />
            )}
          </Card>
          <ServiceStatus tasks={data.queue} reload={reload} />
        </>
      )}
      {tab === 'rides' && <BikeRides bikeId={data.id} onChanged={reload} />}
      {tab === 'incidents' && (
        <Card title="Incidents" className="span-2">
          <BikeIncidents incidents={incidents.data} error={incidents.error} loading={incidents.loading} reload={incidents.reload} bikeName={data.name} />
        </Card>
      )}
      {tab === 'maintenance' && (
        <>
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
          <Card title="Brake circuits">
            {data.brakes.length === 0 ? (
              <Empty title="No brake circuits installed" />
            ) : (
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
            )}
          </Card>
        </>
      )}
      {tab === 'costs' && (
        <>
          <CostCard bike={data} onEdit={() => setSheet({ kind: 'costs' })} />
          <Bundles bikeId={data.id} refresh={data} onChanged={(msg) => { toast(msg); reload() }} className="span-2" />
        </>
      )}
      {tab === 'history' && (
        <>
          <Journal bikeId={data.id} className="span-2" />
          <ChangeLog bikeId={data.id} refresh={data} className="span-2" />
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
        </>
      )}
      {sheet?.kind === 'install' && (
        <Sheet title="Install a part" onClose={() => setSheet(null)}>
          <InstallForm bikeId={data.id} onDone={done} />
        </Sheet>
      )}
      {sheet?.kind === 'costs' && (
        <Sheet title={`Purchase price · ${data.name}`} onClose={() => setSheet(null)}>
          <PurchaseForm
            bike={data}
            onDone={() => {
              setSheet(null)
              toast('Saved.')
              reload()
            }}
          />
        </Sheet>
      )}
      {sheet?.kind === 'groupset' && (
        <Sheet title={`${sheet.replace ? 'Replace whole groupset' : 'Add a groupset'} · ${data.name}`} onClose={() => setSheet(null)}>
          <GroupsetImport
            bikeId={data.id}
            initialOccupied={sheet.replace ? 'REPLACE' : 'KEEP'}
            onDone={(msg) => {
              setSheet(null)
              toast(msg)
              reload()
            }}
          />
        </Sheet>
      )}
      {sheet?.kind === 'wheelset' && (
        <Sheet title={`Group wheels into a wheelset · ${data.name}`} onClose={() => setSheet(null)}>
          <WheelsetForm bikeId={data.id} onDone={done} />
        </Sheet>
      )}
      {sheet?.kind === 'part' && (
        <Sheet title={`Change ${sheet.row.label}`} onClose={() => setSheet(null)}>
          <PartActions row={sheet.row} onDone={done} />
        </Sheet>
      )}
      {sheet?.kind === 'swap' && (
        <Sheet title={`${sheet.title} · ${data.name}`} onClose={() => setSheet(null)}>
          {sheet.title === 'Swap tube' ? (
            <SwapTube
              bikeId={data.id}
              onDone={(text) => {
                setSheet(null)
                toast(text)
                reload()
              }}
            />
          ) : (
            <SwapPart rows={sheet.rows} setup={data.setup} remove={sheet.remove} onDone={done} />
          )}
        </Sheet>
      )}
      {sheet?.kind === 'spokes' && (
        <Sheet title={`Spokes · ${sheet.row.label}`} onClose={() => setSheet(null)}>
          <SpokesForm
            wheel={sheet.row}
            onDone={() => {
              setSheet(null)
              toast('Spokes added.')
              reload()
            }}
          />
        </Sheet>
      )}
      {sheet?.kind === 'retire' && (
        <Sheet title={`Retire or delete · ${data.name}`} onClose={() => setSheet(null)}>
          <RetireBike bike={data} onRetired={() => (setSheet(null), toast(`${data.name} retired. Bikes → Retired bikes shows it; Restore brings it back.`), reload())} />
        </Sheet>
      )}
      {sheet?.kind === 'log' && (
        <Sheet title={`Record work done · ${data.name}`} onClose={() => setSheet(null)}>
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

const isWheel = (r: SetupRow) => r.component_type === 'FRONT_WHEEL' || r.component_type === 'REAR_WHEEL'

// The spokes on a wheel as one part (a set): type, count and lengths (drive / non-drive side on the rear).
function SpokesForm({ wheel, onDone }: { wheel: SetupRow; onDone: () => void }) {
  const rear = wheel.component_type === 'REAR_WHEEL'
  const [f, setF] = useState({ label: `Spokes ${wheel.label}`, model: '', count: '', length: '', drive: '', nondrive: '', nipples: '', at: wheel.since })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const num = (v: string) => (v.trim() ? Number(v.replace(',', '.')) : undefined)
  async function save() {
    setErr(null)
    setBusy(true)
    try {
      const specs = Object.fromEntries(
        Object.entries({ model: f.model.trim() || undefined, count: num(f.count), length_mm: num(f.length), length_drive_mm: num(f.drive), length_non_drive_mm: num(f.nondrive), nipples: f.nipples.trim() || undefined }).filter(([, v]) => v !== undefined),
      )
      if (Object.values(specs).some((v) => typeof v === 'number' && Number.isNaN(v))) throw new Error('Count and lengths are numbers, e.g. 24 or 288')
      await api.post('/components', { component_type: 'SPOKES', label: f.label, prior_usage: 'UNKNOWN', specs, install: { parent_component_id: wheel.component_id, slot: 'SPOKES', at: f.at } }, opId)
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="form">
      <div className="row">
        <Field label="Name">
          <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
        </Field>
        <Field label="Spoke model">
          <input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} placeholder="e.g. Sapim CX-Ray, DT Aerolite" />
        </Field>
      </div>
      <div className="row">
        <Field label="Number of spokes">
          <input inputMode="numeric" value={f.count} onChange={(e) => setF({ ...f, count: e.target.value })} placeholder="e.g. 24" />
        </Field>
        {rear ? (
          <>
            <Field label="Length drive side (mm)">
              <input inputMode="decimal" value={f.drive} onChange={(e) => setF({ ...f, drive: e.target.value })} />
            </Field>
            <Field label="Length non-drive side (mm)">
              <input inputMode="decimal" value={f.nondrive} onChange={(e) => setF({ ...f, nondrive: e.target.value })} />
            </Field>
          </>
        ) : (
          <Field label="Length (mm)">
            <input inputMode="decimal" value={f.length} onChange={(e) => setF({ ...f, length: e.target.value })} />
          </Field>
        )}
      </div>
      <div className="row">
        <Field label="Nipples (optional)">
          <input value={f.nipples} onChange={(e) => setF({ ...f, nipples: e.target.value })} placeholder="e.g. alloy, 14 mm" />
        </Field>
        <Field label="On the wheel since" hint="When the wheel was laced; broken spokes count from here.">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
      </div>
      <p className="small muted">Leave what you don't know empty. Spare spokes for repairs go under Inventory → Add spare stock (type Spokes), so a broken spoke can take one from there.</p>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !f.label.trim()} onClick={save}>
          Add spokes
        </button>
      </div>
    </div>
  )
}

// A bike created by mistake (nothing recorded on it) is deleted for good; any other bike is retired:
// hidden from the list, rides and km kept, restorable. Its parts can come off into storage.
function RetireBike({ bike, onRetired }: { bike: BikeDetail; onRetired: () => void }) {
  const nav = useNavigate()
  const { toast } = useApp()
  const c = bike.history_counts
  const empty = Object.values(c).every((n) => n === 0)
  const [partsOff, setPartsOff] = useState(bike.setup.length > 0)
  const [at, setAt] = useState(today())
  const [err, setErr] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function retire() {
    setErr(null)
    try {
      await api.post(`/bikes/${bike.id}/retire`, partsOff ? { parts_off_at: at } : {}, opId)
      onRetired()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  async function del() {
    if (!window.confirm(`Delete ${bike.name} for good? This cannot be undone.`)) return
    try {
      await api.del(`/bikes/${bike.id}`)
      toast(`${bike.name} deleted.`)
      nav('/bikes')
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      {empty ? (
        <>
          <p>Nothing is recorded on {bike.name} yet (no rides, parts, maintenance or notes), so it can be deleted for good.{bike.strava_gear_id ? ' Strava sync will not create it again; its rides come in without a bike.' : ''}</p>
          <div className="form-actions">
            <button className="btn btn-danger" onClick={del}>
              Delete bike
            </button>
          </div>
          <p className="small muted">Or retire it below if you want to keep it.</p>
        </>
      ) : (
        <p className="small muted">
          {bike.name} has {c.rides} ride{c.rides === 1 ? '' : 's'} and {c.installations} part installation{c.installations === 1 ? '' : 's'} on record, so it is retired instead of deleted: hidden from the bike list, with its rides, km and history kept. You can restore it any time.
        </p>
      )}
      {bike.setup.length > 0 && (
        <label className="check">
          <input type="checkbox" checked={partsOff} onChange={(e) => setPartsOff(e.target.checked)} /> Take its parts off and store them (they keep their km; frame and fork stay with the bike)
        </label>
      )}
      {partsOff && bike.setup.length > 0 && (
        <Field label="Parts off on">
          <input type="date" value={at} onChange={(e) => setAt(e.target.value)} />
        </Field>
      )}
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={retire}>
          Retire bike
        </button>
      </div>
    </div>
  )
}

// Everyday part changes in one place. A swap opens the normal Replace dialog for the part of that type
// on this bike (after a pick when there are several), so spares, stock and carried-over parts work as usual.
function ManageParts({ setup, onSwap, onRemove, onInstall, onWheelset, onReplaceGroupset }: { setup: SetupRow[]; onSwap: (title: string, rows: SetupRow[]) => void; onRemove: (rows: SetupRow[]) => void; onInstall: () => void; onWheelset: () => void; onReplaceGroupset: () => void }) {
  const { meta } = useApp()
  // same grouping as Installed now: drivetrain, brakes, controls and the Di2 / AXS battery
  const groupsetParts = setup.filter((r) => r.component_type === 'BATTERY' || CATEGORY_GROUP[meta.component_types.find((t) => t.code === r.component_type)?.category ?? ''] === 'GROUPSET')
  const of = (t: string) => setup.filter((r) => r.component_type === t)
  const wheelsets = of('WHEELSET')
  const looseWheels = setup.filter((r) => r.depth === 0 && isWheel(r))
  const swaps: [string, string, SetupRow[], string][] = [
    ['Swap chain', 'Swap chain', of('CHAIN'), 'No chain installed'],
    wheelsets.length > 0
      ? ['Swap wheelset', 'Swap wheelset', wheelsets, '']
      : ['Swap wheels', 'Swap a wheel', setup.filter(isWheel), 'No wheels installed'],
    ['Swap tire', 'Swap a tire', of('TIRE'), 'No tires installed'],
    ['Swap tube', 'Swap tube', [], ''],
    ['Swap another part', 'Swap a part', setup, 'Nothing installed yet'],
  ]
  return (
    <Card title="Manage parts" className="span-2">
      <div className="manage-parts">
        <div>
          <h3 className="small muted">Change parts</h3>
          <div className="chips">
            {swaps.map(([label, title, rows, none]) => (
              <button key={label} className="btn" disabled={rows.length === 0 && label !== 'Swap tube'} title={rows.length === 0 ? none || undefined : undefined} onClick={() => onSwap(title, rows)}>
                {label}
              </button>
            ))}
          </div>
          <h4 className="small muted sub-head">Groupset</h4>
          <div className="chips">
            <button className="btn" disabled={groupsetParts.length === 0} title={groupsetParts.length === 0 ? 'No groupset parts on this bike' : 'Change one part, e.g. an Ultegra crankset for a Dura-Ace one'} onClick={() => onSwap('Change a groupset part', groupsetParts)}>
              Change a groupset part
            </button>
            <button className="btn" disabled={groupsetParts.length === 0} title="Put a different groupset on: the old parts come off and keep their km" onClick={onReplaceGroupset}>
              Replace whole groupset
            </button>
          </div>
        </div>
        <div>
          <h3 className="small muted">Add parts</h3>
          <div className="chips">
            <button className="btn" onClick={onInstall}>
              Install a part
            </button>
            {looseWheels.length > 0 && (
              <button className="btn" onClick={onWheelset}>
                Group wheels into a wheelset
              </button>
            )}
          </div>
        </div>
        <div>
          <h3 className="small muted">Remove parts</h3>
          <div className="chips">
            <button className="btn" disabled={setup.length === 0} title={setup.length === 0 ? 'Nothing installed yet' : 'Take a part off without putting another one on'} onClick={() => onRemove(setup)}>
              Remove a part
            </button>
          </div>
        </div>
      </div>
      <p className="small muted">
        A swap takes a stored spare, one from stock or a new item, and the old part keeps its km for next time.
        {wheelsets.length === 0 && looseWheels.length > 0 && ' Wheels swap one at a time; group them into a wheelset to swap both in one go.'} To change one particular part, you can also click it under Installed now.
      </p>
    </Card>
  )
}

function SwapPart({ rows, setup, remove, onDone }: { rows: SetupRow[]; setup: SetupRow[]; remove?: boolean; onDone: (c: Change) => void }) {
  const { meta } = useApp()
  const [picked, setPicked] = useState<number | null>(rows.length === 1 ? rows[0].component_id : null)
  const where = (r: SetupRow) => {
    const parent = setup.find((p) => p.component_id === r.parent_component_id)
    return parent ? `on ${parent.label}` : slotName(r.slot)
  }
  return (
    <div className="form">
      {rows.length > 1 && (
        <fieldset className="field">
          <legend className="field-label">Which one?</legend>
          <div className="pick-list">
            {rows.map((r) => (
              <label key={r.component_id} className={`pick ${picked === r.component_id ? 'pick-on' : ''}`}>
                <input type="radio" name="swap-pick" checked={picked === r.component_id} onChange={() => setPicked(r.component_id)} />
                <span>
                  <strong>{r.label}</strong> <span className="small muted">· {r.type_name} · {where(r)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {picked !== null &&
        (remove ? (
          <RemoveForm key={picked} componentId={picked} suggested={meta.component_types.find((t) => t.code === rows.find((r) => r.component_id === picked)?.component_type)?.removed_default ?? 'STORED'} onDone={(c) => onDone(c)} />
        ) : (
          <ReplaceForm key={picked} componentId={picked} onDone={(c) => onDone(c)} />
        ))}
    </div>
  )
}

// The bike's rides, newest first; a click opens the ride (same view as Rides → ride).
function BikeRides({ bikeId, onChanged }: { bikeId: number; onChanged: () => void }) {
  const { toast } = useApp()
  const { data, error, loading, reload } = useApi<RideRow[]>(`/rides?limit=1000&view=active&bike_id=${bikeId}`)
  const [open, setOpen] = useState<number | null>(null)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const rides = data ?? []
  const totalKm = rides.reduce((a, r) => a + (r.distance_km ?? 0), 0)
  const totalS = rides.reduce((a, r) => a + (r.duration_s ?? 0), 0)
  return (
    <Card title="Rides" className="span-2">
      {rides.length === 0 ? (
        <Empty title="No rides on this bike yet">Add a ride, import a CSV or sync Strava under Rides.</Empty>
      ) : (
        <>
          <p className="small muted">
            {rides.length} ride{rides.length === 1 ? '' : 's'} · {km(totalKm, 0)} · {duration(totalS)} recorded ride time
            {rides.length >= 1000 ? ' (latest 1000 shown)' : ''}
          </p>
          <table className="table rides bike-rides">
            <thead>
              <tr>
                <th>Date</th>
                <th>Name</th>
                <th className="num">Distance</th>
                <th className="num">Time</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {rides.map((r) => (
                <tr key={r.id} onClick={() => setOpen(r.id)}>
                  <td>{when(r.start_time_utc ?? r.ride_date)}</td>
                  <td>
                    <button className="linklike">{r.name || 'Ride'}</button>
                  </td>
                  <td className="num">{km(r.distance_km)}</td>
                  <td className="num">{duration(r.duration_s)}</td>
                  <td>
                    {r.sport_type === 'VirtualRide' && <Tag>indoor</Tag>}
                    {r.conditions === 'WET' && <Tag tone="info">wet</Tag>}
                    {r.incidents > 0 && <Tag tone="bad">{r.incidents} incident{r.incidents === 1 ? '' : 's'}</Tag>}
                    {r.flags.length > 0 && <Tag tone="warn">{r.flags[0].code.replace(/_/g, ' ').toLowerCase()}</Tag>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {open !== null && (
        <Sheet title="Ride" onClose={() => setOpen(null)}>
          <RideDetailView
            id={open}
            onChanged={(c) => {
              if (c?.notice) toast(c.notice)
              reload()
              onChanged()
            }}
          />
        </Sheet>
      )}
    </Card>
  )
}

// Service status: what needs doing first; reminders that need a first entry and those that are fine fold away.
const NEEDS_ACTION = ['OVERDUE', 'DUE', 'DUE_SOON', 'ATTENTION', 'SNOOZED']

function ServiceStatus({ tasks, reload }: { tasks: Task[]; reload: () => void }) {
  const now = tasks.filter((t) => NEEDS_ACTION.includes(t.status))
  const first = tasks.filter((t) => t.status === 'INSUFFICIENT_INFO')
  const fine = tasks.filter((t) => !NEEDS_ACTION.includes(t.status) && t.status !== 'INSUFFICIENT_INFO')
  return (
    <Card title="Service status" className="span-2">
      {tasks.length === 0 ? (
        <Empty title="No rules apply to the installed parts yet." />
      ) : (
        <>
          {now.length ? <TaskList tasks={now} onChange={reload} /> : <p className="small muted">Nothing due right now.</p>}
          {first.length > 0 && (
            <details className="task-group" data-group="first">
              <summary>
                <strong>Need a first entry</strong> <span className="muted small">{first.length} reminders start counting once you log the last time it was done</span>
              </summary>
              <TaskList tasks={first} onChange={reload} />
            </details>
          )}
          {fine.length > 0 && (
            <details className="task-group" data-group="ok">
              <summary>
                <strong>Up to date</strong> <span className="muted small">{fine.length} reminders</span>
              </summary>
              <TaskList tasks={fine} onChange={reload} />
            </details>
          )}
        </>
      )}
    </Card>
  )
}

// "Installed now" in groups (groupset, wheels, cockpit ...): one line each, unfolded with the triangle.
// A part mounted on another part (tire on a wheel) stays with the part it is mounted on.
const SETUP_GROUPS: [string, string][] = [
  ['GROUPSET', 'Groupset (drivetrain, shifting, brakes)'],
  ['WHEELS', 'Wheels and tires'],
  ['COCKPIT', 'Cockpit'],
  ['CONTACT', 'Contact points'],
  ['FRAME', 'Frame'],
  ['ELECTRONICS', 'Electronics'],
  ['OTHER', 'Other'],
]
const CATEGORY_GROUP: Record<string, string> = {
  Drivetrain: 'GROUPSET',
  Brakes: 'GROUPSET',
  Controls: 'GROUPSET',
  Wheels: 'WHEELS',
  Cockpit: 'COCKPIT',
  'Contact points': 'CONTACT',
  Frame: 'FRAME',
  Electronics: 'ELECTRONICS',
}

// One line under each wheel: its spokes (type, count, lengths) and the broken spokes since it was laced.
function SpokeLine({ row, onAdd }: { row: SetupRow; onAdd: () => void }) {
  const sp = row.spokes
  if (!sp) return null
  const s = sp.specs
  const lengths = row.component_type === 'REAR_WHEEL' && (s.length_drive_mm || s.length_non_drive_mm)
    ? `${s.length_drive_mm ?? '?'} mm drive side / ${s.length_non_drive_mm ?? '?'} mm non-drive`
    : s.length_mm
      ? `${s.length_mm} mm`
      : null
  const what = [s.count ? `${s.count} ×` : null, s.model ?? sp.product ?? sp.label, lengths].filter(Boolean).join(' ')
  const tone = sp.broken >= sp.relace_after ? 'bad' : sp.broken === sp.relace_after - 1 ? 'warn' : 'neutral'
  return (
    <span className="spoke-line small">
      Spokes:{' '}
      {sp.component_id ? (
        <>
          <Link to={`/inventory/${sp.component_id}`}>{what}</Link>
          {sp.from_product.length > 0 && <span className="muted"> (from product data, check)</span>}
        </>
      ) : (
        <>
          <span className="muted">not recorded</span>{' '}
          <button className="btn btn-small" onClick={onAdd}>
            Add spokes
          </button>
        </>
      )}{' '}
      <Tag tone={tone}>
        {sp.broken} of {sp.relace_after} broken spokes{sp.since ? ` since ${when(sp.since)}` : ''}
      </Tag>
    </span>
  )
}

function SetupGroups({ setup, groupset, bikeId, onChange, reload, onAddSpokes }: { setup: SetupRow[]; groupset: GroupsetSummary | null; bikeId: number; onChange: (row: SetupRow) => void; reload: () => void; onAddSpokes: (row: SetupRow) => void }) {
  const { meta } = useApp()
  const groupOf = (type: string) => {
    if (type === 'BATTERY') return 'GROUPSET' // Di2 / AXS battery belongs to the shifting
    const cat = meta.component_types.find((t) => t.code === type)?.category ?? ''
    return CATEGORY_GROUP[cat] ?? 'OTHER'
  }
  const groups: Record<string, SetupRow[]> = {}
  let current = 'OTHER'
  for (const s of setup) {
    if (s.depth === 0) current = groupOf(s.component_type)
    ;(groups[current] ??= []).push(s)
  }
  return (
    <div className="setup-groups">
      {SETUP_GROUPS.filter(([k]) => groups[k]?.length).map(([k, label]) => {
        const rows = groups[k]
        const top = rows.filter((r) => r.depth === 0).map((r) => r.label)
        return (
          <details key={k} className="setup-group" data-group={k}>
            {k === 'GROUPSET' && groupset ? (
              // the groupset as one line; its page has the combined km, tasks, log, journal and the parts tree
              <summary>
                <strong>Groupset</strong> <Link to={`/bikes/${bikeId}/groupset`}>{groupset.name === 'Groupset' ? 'open' : groupset.name}</Link>{' '}
                <span className="muted small">
                  {groupset.parts} part{groupset.parts === 1 ? '' : 's'}
                </span>
                {groupset.due > 0 && (
                  <>
                    {' '}
                    <Tag tone="warn">{groupset.due} need attention</Tag>
                  </>
                )}
              </summary>
            ) : (
              <summary>
                <strong>{label}</strong>
                <span className="muted small">
                  {rows.length} part{rows.length === 1 ? '' : 's'} · {top.slice(0, 3).join(', ')}
                  {top.length > 3 ? ', …' : ''}
                </span>
              </summary>
            )}
            <ul className="list setup">
              {rows.map((s) => (
                <li key={s.installation_id} style={{ paddingLeft: `${s.depth * 1.2}rem` }}>
                  <span className="muted small">{slotName(s.slot)}</span>
                  <Link to={`/inventory/${s.component_id}`}>{s.label}</Link>
                  <span className="muted small">since {when(s.since)}</span>
                  {(s.component_type === 'FRONT_WHEEL' || s.component_type === 'REAR_WHEEL') && <TireSetupSelect wheelId={s.component_id} value={s.tire_setup} onSaved={reload} />}
                  {s.component_type === 'TIRE' && <PressureNote tireId={s.component_id} value={s.pressure_note} onSaved={reload} />}
                  <button className="btn btn-small" onClick={() => onChange(s)}>
                    Change
                  </button>
                  {s.spokes && <SpokeLine row={s} onAdd={() => onAddSpokes(s)} />}
                </li>
              ))}
            </ul>
          </details>
        )
      })}
    </div>
  )
}

const COST_KIND: Record<string, string> = { PART: 'part', BUNDLE: 'bundle', STOCK: 'from stock', SERVICE: 'service' }

// Electronic or mechanical shifting: decides whether Di2 checks or cable checks apply to this bike.
function ShiftingSelect({ bike, onSaved }: { bike: BikeDetail; onSaved: () => void }) {
  const { meta, toast } = useApp()
  const label = (code: string | null) => meta.shifting_types.find((t) => t.code === code)?.label.toLowerCase()
  async function save(v: string) {
    try {
      await api.patch(`/bikes/${bike.id}`, { shifting: v || null })
      toast(v ? `Shifting set to ${label(v)}.` : 'Shifting not set.')
      onSaved()
    } catch (e) {
      toast((e as Error).message)
    }
  }
  return (
    <label className="inline-field small">
      Shifting{' '}
      <select aria-label="Shifting" value={bike.shifting ?? ''} onChange={(e) => save(e.target.value)}>
        <option value="">{bike.shifting_effective ? `Not set (${label(bike.shifting_effective)}: battery fitted)` : 'Not set'}</option>
        {meta.shifting_types.map((t) => (
          <option key={t.code} value={t.code}>
            {t.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function CostCard({ bike, onEdit }: { bike: BikeDetail; onEdit: () => void }) {
  const c = bike.cost_detail
  const perKm = bike.usage.total_km > 0 && c.total_cents ? Math.round(c.total_cents / bike.usage.total_km) : null
  const [open, setOpen] = useState(false)
  return (
    <Card
      title="Costs"
      className="span-2"
      actions={
        <button className="btn btn-small" onClick={onEdit}>
          Purchase price
        </button>
      }
    >
      <div className="stats">
        <div>
          <span className="stat">{c.initial_known ? euro(c.initial_cents) : '—'}</span>
          <span className="muted small">initial cost{c.purchase_date ? ` · ${when(c.purchase_date)}` : c.initial_known ? '' : ' · not entered'}</span>
        </div>
        <div>
          <span className="stat">
            {c.estimated ? '≈' : ''}
            {euro(c.running_cents) || euro(0)}
          </span>
          <span className="muted small">
            running cost: {c.bundles_cents > 0 ? `bundles ${euro(c.bundles_cents)} · ` : ''}parts {euro(c.parts_cents) || euro(0)} · from stock {euro(c.stock_cents) || euro(0)} · services {euro(c.services_cents) || euro(0)}
          </span>
        </div>
        <div>
          <span className="stat">{euro(c.total_cents) || euro(0)}</span>
          <span className="muted small">total{perKm !== null ? ` · ${bike.usage.certainty === 'INCOMPLETE' ? 'at most ' : ''}${euro(perKm)} per km` : ''}</span>
        </div>
      </div>
      {(c.unpriced_parts > 0 || c.estimated || c.unpriced_bundles > 0) && (
        <p className="small muted">
          {c.unpriced_bundles > 0 && `${c.unpriced_bundles} bundle${c.unpriced_bundles === 1 ? ' has' : 's have'} no price yet. `}
          {c.unpriced_parts > 0 &&
            `${c.unpriced_parts} installed part${c.unpriced_parts === 1 ? ' has' : 's have'} no price${
              c.unpriced_labels?.length ? ` (${c.unpriced_labels.slice(0, 5).join(', ')}${c.unpriced_labels.length > 5 ? ', …' : ''})` : ''
            }; fine for parts that came with the bike. `}
          {c.estimated && '≈: parts taken from stock are valued at the average price paid for that stock.'}
        </p>
      )}
      {(c.items?.length ?? 0) > 0 && (
        <>
          <button className="btn btn-small" onClick={() => setOpen(!open)}>
            {open ? 'Hide' : 'Show'} {c.items?.length} cost entries
          </button>
          {open && (
            <ul className="list">
              {c.items?.map((i, n) => (
                <li key={n}>
                  <span className="muted small">{when(i.date)}</span>
                  <span>{i.component_id ? <Link to={`/inventory/${i.component_id}`}>{i.text}</Link> : i.text}</span>
                  <Tag>{COST_KIND[i.kind]}</Tag>
                  <span>
                    {i.estimated ? '≈' : ''}
                    {euro(i.cents)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  )
}

function PurchaseForm({ bike, onDone }: { bike: Bike; onDone: () => void }) {
  const [f, setF] = useState({ price: centsInput(bike.purchase_price_cents), date: bike.purchase_date ?? '' })
  const [err, setErr] = useState<string | null>(null)
  async function save() {
    setErr(null)
    const price = toCents(f.price)
    if (Number.isNaN(price)) return setErr('Price: enter an amount such as 3499,00')
    try {
      await api.patch(`/bikes/${bike.id}`, { purchase_price_cents: price, purchase_date: f.date || null })
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      <div className="row">
        <Field label="Purchase price" hint="What you paid for the bike, including the parts it came with.">
          <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="€" autoFocus />
        </Field>
        <Field label="Bought on">
          <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
        </Field>
      </div>
      <p className="small muted">Running cost is added up from part prices, stock used on this bike and service costs; it is never typed in.</p>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={save}>
          Save
        </button>
      </div>
    </div>
  )
}

function WheelsetForm({ bikeId, onDone }: { bikeId: number; onDone: (c: Change) => void }) {
  const [f, setF] = useState({ label: '', at: today() })
  const [preview, setPreview] = useState<Change | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function run(dry: boolean) {
    setErr(null)
    try {
      const r = await api.post<OpResult<unknown>>(`/bikes/${bikeId}/group-wheels${dry ? '?dry_run=true' : ''}`, { at: f.at, label: f.label || null }, dry ? undefined : opId)
      if (dry) setPreview(r.change)
      else onDone(r.change)
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      <p className="small muted">
        The front and rear wheel go into one wheelset with everything on them (tires, tubes, rotors, cassette, sensors). Each part keeps its own km. From then on you can move
        the whole wheelset to another bike in one step. The wheelset itself counts km from this date; add its km from before on its page if you know them.
      </p>
      <div className="row">
        <Field label="Wheelset name">
          <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="e.g. Reynolds AR58" />
        </Field>
        <Field label="From">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
      </div>
      <ChangeNotice change={preview} />
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn" onClick={() => run(true)}>
          Preview
        </button>
        <button className="btn btn-primary" onClick={() => run(false)}>
          Group wheels
        </button>
      </div>
    </div>
  )
}
