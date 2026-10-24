import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, newOpId } from '../api'
import LogMaintenance from '../components/LogMaintenance'
import TaskList from '../components/TaskList'
import { Card, ChangeNotice, Empty, ErrorBox, Field, FormError, Loading, Sheet, Tag } from '../components/ui'
import { useApp } from '../context'
import { certaintyLabel, km, slotName, today, usageText, when } from '../format'
import { useApi } from '../hooks'
import type { Bike, Change, ChainRow, ComponentSummary, EventRow, OpResult, Rule, Task } from '../types'

const CHAIN_TONE: Record<string, 'good' | 'warn' | 'info' | 'bad' | 'neutral'> = {
  READY_TO_INSTALL: 'good',
  INSTALLED: 'info',
  NEEDS_HOT_WAX: 'warn',
  NEW_UNWAXED: 'warn',
  WORN: 'bad',
  UNKNOWN: 'neutral',
  RETIRED: 'neutral',
}

export function ChainStateTag({ state }: { state: string }) {
  return <Tag tone={CHAIN_TONE[state] ?? 'neutral'}>{state.replace(/_/g, ' ').toLowerCase()}</Tag>
}

export function ComponentForm({ onSaved, presetType }: { onSaved: (c: ComponentSummary) => void; presetType?: string }) {
  const { meta } = useApp()
  const bikes = useApi<Bike[]>('/bikes')
  const [f, setF] = useState({ component_type: presetType ?? 'CHAIN', label: '', history: 'NEW', start_km: '', start_date: today(), start_estimate: true, install_bike: '', install_slot: '', install_at: today(), notes: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const ctype = meta.component_types.find((t) => t.code === f.component_type)
  const canInstallOnBike = ctype && !['TIRE', 'BRAKE_ROTOR'].includes(ctype.code)
  async function save() {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { component_type: f.component_type, label: f.label, prior_usage: f.history === 'KNOWN' ? 'UNKNOWN' : f.history }
      if (f.notes) body.notes = f.notes
      if (f.history === 'KNOWN') Object.assign(body, { starting_km: Number(f.start_km || 0), starting_date: f.start_date, starting_is_estimate: f.start_estimate })
      if (f.install_bike) body.install = { bike_id: Number(f.install_bike), at: f.install_at, ...(f.install_slot ? { slot: f.install_slot } : {}) }
      onSaved(await api.post<ComponentSummary>('/components', body, opId))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="form">
      <div className="row">
        <Field label="Type">
          <select value={f.component_type} onChange={(e) => setF({ ...f, component_type: e.target.value, install_slot: '' })}>
            {meta.component_types.map((t) => (
              <option key={t.code} value={t.code}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Name / label" hint="e.g. Chain A. Specs can be added later.">
          <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} autoFocus />
        </Field>
      </div>
      <Field label="Usage before tracking">
        <select value={f.history} onChange={(e) => setF({ ...f, history: e.target.value })}>
          <option value="NEW">New part (0 km)</option>
          <option value="KNOWN">I know (or can estimate) its km</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </Field>
      {f.history === 'KNOWN' && (
        <>
          <div className="row">
            <Field label="km at that date">
              <input inputMode="decimal" value={f.start_km} onChange={(e) => setF({ ...f, start_km: e.target.value })} />
            </Field>
            <Field label="As of">
              <input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
            </Field>
          </div>
          <label className="check">
            <input type="checkbox" checked={f.start_estimate} onChange={(e) => setF({ ...f, start_estimate: e.target.checked })} /> This is an estimate
          </label>
        </>
      )}
      {canInstallOnBike && (
        <div className="row">
          <Field label="Install on (optional)">
            <select value={f.install_bike} onChange={(e) => setF({ ...f, install_bike: e.target.value })}>
              <option value="">Keep in storage</option>
              {bikes.data?.filter((b) => b.status === 'ACTIVE').map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </Field>
          {f.install_bike && ctype && ctype.slots.length > 1 && (
            <Field label="Position">
              <select value={f.install_slot} onChange={(e) => setF({ ...f, install_slot: e.target.value })}>
                <option value="">Pick…</option>
                {ctype.slots.map((s) => (
                  <option key={s} value={s}>
                    {slotName(s)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {f.install_bike && (
            <Field label="Since">
              <input type="date" value={f.install_at} onChange={(e) => setF({ ...f, install_at: e.target.value })} />
            </Field>
          )}
        </div>
      )}
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !f.label.trim()} onClick={save}>
          {busy ? 'Saving…' : 'Add part'}
        </button>
      </div>
    </div>
  )
}

export default function InventoryPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'parts'
  const [state, setState] = useState('')
  const [adding, setAdding] = useState(false)
  const nav = useNavigate()
  const parts = useApi<ComponentSummary[]>(tab === 'parts' ? `/components${state ? `?state=${state}` : ''}` : null)
  const chains = useApi<ChainRow[]>(tab === 'chains' ? '/chains' : null)
  const cons = useApi<{ id: number; kind: string; name: string; unit: string; track_stock: boolean; stock: { qty: number; known: boolean } | null; purchases: number; uses: number }[]>(tab === 'consumables' ? '/consumables' : null)
  return (
    <Card title="Inventory" actions={<button className="btn btn-primary" onClick={() => setAdding(true)}>Add part</button>}>
      <div className="tabs" role="tablist">
        {[
          ['parts', 'Parts'],
          ['chains', 'Chains'],
          ['consumables', 'Consumables'],
        ].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'tab-on' : ''}`} onClick={() => setParams({ tab: k })}>
            {l}
          </button>
        ))}
      </div>
      {tab === 'parts' && (
        <>
          <div className="filters">
            <select value={state} onChange={(e) => setState(e.target.value)} aria-label="Filter">
              <option value="">All parts</option>
              <option value="INSTALLED">Installed</option>
              <option value="STORED">Spares in storage</option>
              <option value="RETIRED">Retired</option>
            </select>
          </div>
          {parts.loading && !parts.data && <Loading />}
          {parts.error && <ErrorBox error={parts.error} onRetry={parts.reload} />}
          {parts.data?.length === 0 && <Empty title="No parts here">Add a part with just a type and a name.</Empty>}
          {parts.data && parts.data.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Part</th>
                  <th>Type</th>
                  <th>Where</th>
                  <th className="num">Usage</th>
                </tr>
              </thead>
              <tbody>
                {parts.data.map((c) => (
                  <tr key={c.id} onClick={() => nav(`/inventory/${c.id}`)} className={c.status === 'RETIRED' ? 'excluded' : ''}>
                    <td>
                      <Link to={`/inventory/${c.id}`}>{c.label}</Link>
                    </td>
                    <td>{c.type_name}</td>
                    <td>{c.location.text}</td>
                    <td className="num" title={certaintyLabel(c.usage)}>
                      {usageText(c.usage)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {tab === 'chains' && (
        <>
          {chains.loading && !chains.data && <Loading />}
          {chains.error && <ErrorBox error={chains.error} onRetry={chains.reload} />}
          {chains.data?.length === 0 && <Empty title="No chains yet">Add Chain A, B and C to rotate waxed chains.</Empty>}
          <div className="cards">
            {chains.data?.map((c) => (
              <Link to={`/inventory/${c.component_id}`} key={c.component_id} className="tile">
                <strong>{c.label}</strong>
                <ChainStateTag state={c.state} />
                <span className="small">{c.text}</span>
                <span className="muted small">
                  Lifetime {km(c.lifetime_km, 0)}
                  {c.last_wear ? ` · wear ${c.last_wear.value ?? '?'}${c.last_wear.unit ?? ''} on ${when(c.last_wear.date)}` : ' · wear not measured'}
                </span>
              </Link>
            ))}
          </div>
        </>
      )}
      {tab === 'consumables' && <Consumables data={cons.data} loading={cons.loading} error={cons.error} reload={cons.reload} />}
      {adding && (
        <Sheet title="Add part" onClose={() => setAdding(false)}>
          <ComponentForm presetType={tab === 'chains' ? 'CHAIN' : undefined} onSaved={(c) => nav(`/inventory/${c.id}`)} />
        </Sheet>
      )}
    </Card>
  )
}

function Consumables({ data, loading, error, reload }: { data: { id: number; kind: string; name: string; unit: string; track_stock: boolean; stock: { qty: number; known: boolean } | null; purchases: number; uses: number }[] | null; loading: boolean; error: string | null; reload: () => void }) {
  const [f, setF] = useState({ kind: 'WAX', name: '', unit: 'ml', track_stock: false })
  const [buy, setBuy] = useState<{ id: number; qty: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  async function add() {
    setErr(null)
    try {
      await api.post('/consumables', f)
      setF({ ...f, name: '' })
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  async function purchase() {
    if (!buy) return
    setErr(null)
    try {
      await api.post(`/consumables/${buy.id}/txn`, { kind: 'PURCHASE', qty: buy.qty ? Number(buy.qty) : null, on: today() })
      setBuy(null)
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <>
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data?.length === 0 && <Empty title="No consumables yet">Wax, lube, sealant and brake fluid are tracked by product; stock is optional.</Empty>}
      {data && data.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Kind</th>
              <th>Stock</th>
              <th>Bought / used</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.kind.toLowerCase()}</td>
                <td>{c.stock ? `${c.stock.qty} ${c.unit}${c.stock.known ? '' : ' (some uses unknown)'}` : 'not tracked'}</td>
                <td>
                  {c.purchases} / {c.uses}
                </td>
                <td>
                  {buy?.id === c.id ? (
                    <span className="row">
                      <input inputMode="decimal" placeholder={c.unit} value={buy.qty} onChange={(e) => setBuy({ id: c.id, qty: e.target.value })} />
                      <button className="btn btn-small btn-primary" onClick={purchase}>
                        Save
                      </button>
                    </span>
                  ) : (
                    <button className="btn btn-small" onClick={() => setBuy({ id: c.id, qty: '' })}>
                      Record purchase
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Add a consumable</h3>
      <div className="row">
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} aria-label="Kind">
          {['WAX', 'LUBE', 'SEALANT', 'BRAKE_FLUID', 'GREASE', 'OTHER'].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Product name" aria-label="Product name" />
        <input value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} aria-label="Unit" style={{ maxWidth: '5rem' }} />
        <label className="check">
          <input type="checkbox" checked={f.track_stock} onChange={(e) => setF({ ...f, track_stock: e.target.checked })} /> track stock
        </label>
        <button className="btn" disabled={!f.name} onClick={add}>
          Add
        </button>
      </div>
      <FormError error={err} />
    </>
  )
}

interface ComponentDetail extends ComponentSummary {
  ledger: { kind: string; date: string; km: number; ride_id?: number; ride_name?: string | null; bike?: string; slot?: string; basis?: string; counted: boolean; certain: boolean; is_estimate?: boolean; detail: string | null; running_km: number; state?: string }[]
  history: { id: number; where: string; slot: string; installed_at: string; removed_at: string | null; removal_reason: string | null; voided: boolean; void_reason: string | null; km: number | null; note: string | null }[]
  service_status: Task[]
  rules: Rule[]
  events: EventRow[]
  actions: { code: string; name: string }[]
  specs: Record<string, unknown>
}

function RuleEditor({ rule, componentId, onDone }: { rule: Rule; componentId: number; onDone: () => void }) {
  const [f, setF] = useState({ interval_km: rule.interval_km?.toString() ?? '', interval_months: rule.interval_months?.toString() ?? '', window_min_km: rule.window_min_km?.toString() ?? '', window_max_km: rule.window_max_km?.toString() ?? '', origin: rule.origin === 'DEFAULT' ? 'PERSONAL' : rule.origin, scope: 'part' })
  const [err, setErr] = useState<string | null>(null)
  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  async function save(active = true) {
    setErr(null)
    const body: Record<string, unknown> = { origin: f.origin, active }
    if (rule.trigger === 'INTERVAL') Object.assign(body, { interval_km: num(f.interval_km), interval_months: num(f.interval_months) })
    else Object.assign(body, { window_min_km: num(f.window_min_km), window_max_km: num(f.window_max_km) })
    try {
      if (f.scope === 'type' && rule.component_type) await api.patch(`/rules/${rule.id}`, body)
      else await api.post(`/components/${componentId}/rules`, { rule_code: rule.rule_code, ...body })
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      {rule.trigger === 'INTERVAL' ? (
        <div className="row">
          <Field label="Every … km">
            <input inputMode="decimal" value={f.interval_km} onChange={(e) => setF({ ...f, interval_km: e.target.value })} />
          </Field>
          <Field label="or every … months">
            <input inputMode="numeric" value={f.interval_months} onChange={(e) => setF({ ...f, interval_months: e.target.value })} />
          </Field>
        </div>
      ) : (
        <div className="row">
          <Field label="Window from … km">
            <input inputMode="decimal" value={f.window_min_km} onChange={(e) => setF({ ...f, window_min_km: e.target.value })} />
          </Field>
          <Field label="to … km (after the cycle start)">
            <input inputMode="decimal" value={f.window_max_km} onChange={(e) => setF({ ...f, window_max_km: e.target.value })} />
          </Field>
        </div>
      )}
      <div className="row">
        <Field label="Source">
          <select value={f.origin} onChange={(e) => setF({ ...f, origin: e.target.value })}>
            <option value="PERSONAL">Personal interval</option>
            <option value="MANUFACTURER">Manufacturer interval</option>
          </select>
        </Field>
        {rule.component_type && (
          <Field label="Apply to">
            <select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>
              <option value="part">This part only</option>
              <option value="type">All parts of this type</option>
            </select>
          </Field>
        )}
      </div>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn" onClick={() => save(false)}>
          Turn off for this part
        </button>
        <button className="btn btn-primary" onClick={() => save(true)}>
          Save rule
        </button>
      </div>
    </div>
  )
}

export function ComponentDetailPage() {
  const { id } = useParams()
  const { toast, meta } = useApp()
  const actionName = (code: string | null) => (meta.actions.find((a) => a.code === code)?.name ?? code ?? '').toLowerCase()
  const { data, error, loading, reload } = useApi<ComponentDetail>(`/components/${id}`)
  const [sheet, setSheet] = useState<null | 'log' | 'start' | 'retire' | 'rule' | { rule: Rule } | { correct: number }>(null)
  const [f, setF] = useState({ km: '', date: today(), estimate: true, reason: '', installed_at: '', removed_at: '', action_code: 'INSPECT', interval_km: '', interval_months: '' })
  const [preview, setPreview] = useState<Change | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const close = () => {
    setSheet(null)
    setPreview(null)
    setErr(null)
  }
  async function op(path: string, body: unknown, dry = false) {
    setErr(null)
    try {
      const r = await api.post<OpResult<unknown>>(`${path}${dry ? '?dry_run=true' : ''}`, body)
      if (dry) return setPreview(r.change)
      toast(r.change?.notice ?? 'Saved.')
      close()
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  async function plain(path: string, body: unknown) {
    setErr(null)
    try {
      await api.post(path, body)
      close()
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  const u = data.usage
  return (
    <div className="grid">
      <Card
        className="span-2"
        title={
          <>
            {data.label} <span className="muted small">{data.type_name}</span>
          </>
        }
        actions={
          data.status !== 'RETIRED' && (
            <>
              <button className="btn btn-primary" onClick={() => setSheet('log')}>
                Log maintenance
              </button>
              <button className="btn" onClick={() => setSheet('start')}>
                Starting km
              </button>
              <button className="btn" onClick={() => setSheet('retire')}>
                Retire
              </button>
            </>
          )
        }
      >
        <div className="stats">
          <div>
            <span className="stat">{usageText(u)}</span>
            <span className="muted small">{certaintyLabel(u)}</span>
          </div>
          <div>
            <span className="stat">{u.ride_count}</span>
            <span className="muted small">rides</span>
          </div>
          <div>
            <span className="stat">{data.location.state === 'INSTALLED' ? 'Installed' : data.location.state === 'STORED' ? 'In storage' : 'Retired'}</span>
            {data.location.state === 'INSTALLED' && <span className="muted small">{data.location.text}</span>}
          </div>
        </div>
        <p className="small">{u.summary}</p>
        {data.product && <p className="small muted">Product: {data.product}</p>}
      </Card>
      <Card title="Service status" className="span-2">
        <TaskList tasks={data.service_status} onChange={reload} emptyText="No service rules for this part." />
        <div className="form-actions">
          <button className="btn btn-small" onClick={() => setSheet('rule')}>
            Add a rule for this part
          </button>
        </div>
      </Card>
      <Card title="Rules">
        {data.rules.length === 0 ? (
          <Empty title="No rules" />
        ) : (
          <ul className="list">
            {data.rules.map((r) => (
              <li key={r.id}>
                <span>
                  {r.name}
                  {!r.active && <Tag>off</Tag>}
                </span>
                <span className="muted small">
                  {r.trigger === 'CYCLE_WINDOW' ? `once at ${r.window_min_km}–${r.window_max_km} km after ${actionName(r.cycle_action_code)}` : [r.interval_km && `every ${r.interval_km} km`, r.interval_months && `every ${r.interval_months} months`].filter(Boolean).join(' or ')}
                  {' · '}
                  {r.component_id ? 'this part' : 'type default'} · {r.origin.toLowerCase()}
                </span>
                <button className="btn btn-small" onClick={() => setSheet({ rule: r })}>
                  Edit
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Installation history">
        {data.history.length === 0 ? (
          <Empty title="Never installed" />
        ) : (
          <ul className="list">
            {data.history.map((h) => (
              <li key={h.id} className={h.voided ? 'excluded' : ''}>
                <span>{h.where}</span>
                <span className="small">
                  {when(h.installed_at)} → {h.removed_at ? when(h.removed_at) : 'now'}
                </span>
                <span className="small">{h.voided ? `void: ${h.void_reason}` : km(h.km)}</span>
                {!h.voided && (
                  <button className="btn btn-small" onClick={() => { setF({ ...f, installed_at: h.installed_at.slice(0, 10), removed_at: h.removed_at?.slice(0, 10) ?? '' }); setSheet({ correct: h.id }) }}>
                    Correct
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Where the kilometres come from" className="span-2">
        {data.ledger.length === 0 ? (
          <Empty title="No usage recorded yet" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Source</th>
                <th>Bike</th>
                <th className="num">km</th>
                <th className="num">Running</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {data.ledger.map((e, i) => (
                <tr key={i} className={e.counted ? '' : 'excluded'}>
                  <td>{when(e.date)}</td>
                  <td>{e.kind === 'RIDE' ? <Link to={`/rides?open=${e.ride_id}`}>{e.ride_name || 'Ride'}</Link> : e.kind === 'STARTING' ? 'Starting value' : 'Correction'}</td>
                  <td>{e.bike ?? ''}</td>
                  <td className="num">
                    {e.is_estimate ? '≈' : ''}
                    {km(e.km)}
                  </td>
                  <td className="num">{km(e.running_km, 0)}</td>
                  <td className="small">
                    {e.basis === 'EXPLICIT' && <Tag tone="info">confirmed</Tag>}
                    {!e.certain && <Tag tone="warn">{e.is_estimate ? 'estimate' : 'uncertain'}</Tag>}
                    {e.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Maintenance log" className="span-2">
        {data.events.length === 0 ? (
          <Empty title="Nothing logged yet" />
        ) : (
          <ul className="list">
            {data.events.map((e) => (
              <li key={e.id} className={e.voided ? 'excluded' : ''}>
                <span>{when(e.performed_at)}</span>
                <strong>{e.action}</strong>
                <span className="small">{[e.symptom && `symptom: ${e.symptom}`, e.work_done, e.outcome && `→ ${e.outcome.toLowerCase()}`, e.measurement_value !== null && `${e.measurement_value}${e.measurement_unit ?? ''}`, e.consumable].filter(Boolean).join(' · ')}</span>
                {e.voided ? (
                  <Tag>void: {e.void_reason}</Tag>
                ) : (
                  <button
                    className="btn btn-small"
                    onClick={() => {
                      const reason = window.prompt('Why is this entry wrong?')
                      if (reason) plain(`/maintenance/events/${e.id}/void`, { reason })
                    }}
                  >
                    Void
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {sheet === 'log' && (
        <Sheet title={`Log maintenance · ${data.label}`} onClose={close}>
          <LogMaintenance componentId={data.id} onDone={(msg) => { close(); toast(msg); reload() }} />
        </Sheet>
      )}
      {sheet === 'start' && (
        <Sheet title="Starting mileage" onClose={close}>
          <div className="form">
            <p className="small muted">The part had this many km on the given date. Rides before that date are treated as already inside this value.</p>
            <div className="row">
              <Field label="km">
                <input inputMode="decimal" value={f.km} onChange={(e) => setF({ ...f, km: e.target.value })} />
              </Field>
              <Field label="As of">
                <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
              </Field>
            </div>
            <label className="check">
              <input type="checkbox" checked={f.estimate} onChange={(e) => setF({ ...f, estimate: e.target.checked })} /> Estimate
            </label>
            <ChangeNotice change={preview} />
            <FormError error={err} />
            <div className="form-actions">
              <button className="btn" onClick={() => op(`/components/${data.id}/starting-usage`, { km: Number(f.km), effective: f.date, is_estimate: f.estimate }, true)}>
                Preview
              </button>
              <button className="btn btn-primary" onClick={() => op(`/components/${data.id}/starting-usage`, { km: Number(f.km), effective: f.date, is_estimate: f.estimate })}>
                Save
              </button>
            </div>
          </div>
        </Sheet>
      )}
      {sheet === 'retire' && (
        <Sheet title={`Retire ${data.label}`} onClose={close}>
          <div className="form">
            <p className="small muted">The part and its history are kept. It is removed from its bike on that date.</p>
            <Field label="Retired on">
              <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
            </Field>
            <Field label="Reason">
              <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="worn 0.5%" />
            </Field>
            <FormError error={err} />
            <div className="form-actions">
              <button className="btn btn-danger" onClick={() => plain(`/components/${data.id}/retire`, { on: f.date, reason: f.reason || null })}>
                Retire
              </button>
            </div>
          </div>
        </Sheet>
      )}
      {sheet === 'rule' && (
        <Sheet title="Add a rule for this part" onClose={close}>
          <div className="form">
            <Field label="Action">
              <select value={f.action_code} onChange={(e) => setF({ ...f, action_code: e.target.value })}>
                {data.actions.map((a) => (
                  <option key={a.code} value={a.code}>
                    {a.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="row">
              <Field label="Every … km">
                <input inputMode="decimal" value={f.interval_km} onChange={(e) => setF({ ...f, interval_km: e.target.value })} />
              </Field>
              <Field label="or every … months">
                <input inputMode="numeric" value={f.interval_months} onChange={(e) => setF({ ...f, interval_months: e.target.value })} />
              </Field>
            </div>
            <FormError error={err} />
            <div className="form-actions">
              <button
                className="btn btn-primary"
                onClick={() =>
                  plain(`/components/${data.id}/rules`, {
                    action_code: f.action_code,
                    interval_km: f.interval_km ? Number(f.interval_km) : null,
                    interval_months: f.interval_months ? Number(f.interval_months) : null,
                  })
                }
              >
                Add rule
              </button>
            </div>
          </div>
        </Sheet>
      )}
      {sheet && typeof sheet === 'object' && 'rule' in sheet && (
        <Sheet title={`Edit: ${sheet.rule.name}`} onClose={close}>
          <RuleEditor rule={sheet.rule} componentId={data.id} onDone={() => { close(); reload() }} />
        </Sheet>
      )}
      {sheet && typeof sheet === 'object' && 'correct' in sheet && (
        <Sheet title="Correct installation record" onClose={close}>
          <div className="form">
            <p className="small muted">Use this when the record is wrong (a correction), not when you swapped parts.</p>
            <div className="row">
              <Field label="Installed on">
                <input type="date" value={f.installed_at} onChange={(e) => setF({ ...f, installed_at: e.target.value })} />
              </Field>
              <Field label="Removed on">
                <input type="date" value={f.removed_at} onChange={(e) => setF({ ...f, removed_at: e.target.value })} />
              </Field>
            </div>
            <Field label="Why">
              <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
            </Field>
            <ChangeNotice change={preview} />
            <FormError error={err} />
            <div className="form-actions">
              <button className="btn" onClick={() => op(`/installations/${sheet.correct}/correct`, { installed_at: f.installed_at || null, removed_at: f.removed_at || null, clear_removed: !f.removed_at, reason: f.reason }, true)}>
                Preview mileage impact
              </button>
              <button className="btn" onClick={() => op(`/installations/${sheet.correct}/void`, { reason: f.reason || 'record was wrong' })}>
                Record was wrong: void it
              </button>
              <button className="btn btn-primary" onClick={() => op(`/installations/${sheet.correct}/correct`, { installed_at: f.installed_at || null, removed_at: f.removed_at || null, clear_removed: !f.removed_at, reason: f.reason })}>
                Save correction
              </button>
            </div>
          </div>
        </Sheet>
      )}
    </div>
  )
}
