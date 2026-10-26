import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, newOpId } from '../api'
import ChangeLog from '../components/ChangeLog'
import Journal from '../components/Journal'
import LogMaintenance from '../components/LogMaintenance'
import MountPicker, { type MountTarget } from '../components/MountPicker'
import PartTree from '../components/PartTree'
import ProductImport from '../components/ProductImport'
import { DispositionForm, MoveForm, OutcomeChoice, RemoveForm, ReplaceForm } from '../components/PartChange'
import TaskList from '../components/TaskList'
import { PressureNote, TireSetupSelect } from '../components/TireSetup'
import { Card, ChangeNotice, Empty, ErrorBox, Field, FormError, Loading, Sheet, Tag } from '../components/ui'
import { useApp } from '../context'
import { centsInput, certaintyLabel, euro, km, setupLabel, slotName, toCents, today, usageText, when } from '../format'
import { useApi } from '../hooks'
import type { Bike, Change, ChainRow, ComponentSummary, EventRow, OpResult, PartNode, Rule, ShoppingItem, Task } from '../types'

const SUPPLY_KINDS: Record<string, string> = { WAX: 'Chain wax', LUBE: 'Chain lube', SEALANT: 'Tubeless sealant', BRAKE_FLUID: 'Brake fluid', GREASE: 'Grease', OTHER: 'Other' }
// "g" and "ml" stay as they are; "tube" becomes "tubes"
const unitPlural = (u: string) => (u.length <= 2 || u.endsWith('s') ? u : `${u}s`)

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
  const [f, setF] = useState({ component_type: presetType ?? 'CHAIN', label: '', history: 'NEW', start_km: '', start_date: today(), start_estimate: true, install_slot: '', install_at: today(), notes: '', price: '', purchase_date: '' })
  const [mount, setMount] = useState<MountTarget | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  async function save() {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { component_type: f.component_type, label: f.label, prior_usage: f.history === 'KNOWN' ? 'UNKNOWN' : f.history }
      if (f.notes) body.notes = f.notes
      const price = toCents(f.price)
      if (Number.isNaN(price)) throw new Error('Price: enter an amount such as 49,90')
      if (price !== null) body.price_cents = price
      if (f.purchase_date) body.purchase_date = f.purchase_date
      if (f.history === 'KNOWN') Object.assign(body, { starting_km: Number(f.start_km || 0), starting_date: f.start_date, starting_is_estimate: f.start_estimate })
      if (mount) {
        const slot = mount.slot ?? f.install_slot.trim().toUpperCase().replace(/\s+/g, '_')
        if (!slot) throw new Error('Name the position on the bike, e.g. bottle cage 1')
        body.install = { at: f.install_at, slot, ...(mount.parent_component_id ? { parent_component_id: mount.parent_component_id } : { bike_id: mount.bike_id }) }
      }
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
          <select
            value={f.component_type}
            onChange={(e) => {
              setF({ ...f, component_type: e.target.value, install_slot: '' })
              setMount(null)
            }}
          >
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
      <div className="row">
        <Field label="Price paid (optional)" hint="Counts as running cost of the bike it is first installed on.">
          <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="€" />
        </Field>
        <Field label="Bought on (optional)">
          <input type="date" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} />
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
      <MountPicker key={f.component_type} componentType={f.component_type} value={mount} onChange={setMount} allowSpare />
      <div className="row">
        {mount && mount.slot === null && (
          <Field label="Position name">
            <input value={f.install_slot} onChange={(e) => setF({ ...f, install_slot: e.target.value })} placeholder="e.g. bottle cage 1" />
          </Field>
        )}
        {mount && (
          <Field label="Since">
            <input type="date" value={f.install_at} onChange={(e) => setF({ ...f, install_at: e.target.value })} />
          </Field>
        )}
      </div>
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !f.label.trim()} onClick={save}>
          {busy ? 'Saving…' : 'Add part'}
        </button>
      </div>
    </div>
  )
}

interface ItemRow {
  id: number
  label: string
  type_name: string
  component_type: string
  product: string | null
  state: string
  state_text: string
  readiness: string | null
  readiness_text: string | null
  condition: 'NEW' | 'USED'
  storage_location: string | null
  location: { text: string }
  usage: ComponentSummary['usage']
  compatibility: { bike: string | null; verified: boolean }[]
}

interface StockLine {
  id: number
  name: string
  kind: string
  unit: string
  unit_note: string | null
  tracking_mode: 'COUNTED' | 'BULK'
  component_type: string | null
  product_id: number | null
  product: string | null
  storage_location: string | null
  min_stock: number | null
  track_stock: boolean
  stock: { qty: number; known: boolean } | null
  individual_spares: { id: number; label: string }[]
  available_total: number | null
  low: boolean
  purchases: number
  uses: number
  spent_cents: number
  compatibility: { bike: string | null; verified: boolean }[]
}

interface WorkSessionRow {
  id: number
  performed_at: string
  title: string | null
  undone_at: string | null
  undo_reason: string | null
  cost_cents: number
  transactions: { kind: string; text: string; voided?: boolean }[]
}

interface InventoryView {
  stock: StockLine[]
  supplies: StockLine[]
  available: ItemRow[]
  needs_service: ItemRow[]
  installed: ItemRow[]
  out_of_use: ItemRow[]
  shopping_list: ShoppingItem[]
  history: { component_id: number; label: string; text: string; on: string; note: string | null; voided: boolean }[]
  sessions: WorkSessionRow[]
}

const TABS: [string, string][] = [
  ['available', 'Available spares'],
  ['service', 'Needs prep / repair'],
  ['installed', 'Installed'],
  ['shopping', 'Shopping list'],
  ['history', 'History'],
  ['chains', 'Chains'],
  ['supplies', 'Supplies'],
  ['all', 'All parts'],
]

const plural = (n: number, unit: string) => {
  if (n === 1 || /s$/.test(unit)) return `${n.toLocaleString()} ${unit}`
  return `${n.toLocaleString()} ${unit}${/(ch|sh|x)$/.test(unit) ? 'es' : 's'}`
}

function Compat({ rows }: { rows: { bike: string | null; verified: boolean }[] }) {
  if (!rows.length) return null
  return (
    <span className="small">
      {' · fits '}
      {rows.map((r, i) => (
        <span key={i}>
          {i > 0 && ', '}
          {r.bike}
          {!r.verified && <span className="muted"> (unverified)</span>}
        </span>
      ))}
    </span>
  )
}

function ItemList({ rows, empty }: { rows: ItemRow[]; empty: string }) {
  const [type, setType] = useState('')
  const [q, setQ] = useState('')
  const types = Array.from(new Set(rows.map((r) => r.type_name))).sort()
  const shown = rows.filter((r) => (!type || r.type_name === type) && (!q || `${r.label} ${r.product ?? ''} ${r.storage_location ?? ''}`.toLowerCase().includes(q.toLowerCase())))
  if (!rows.length) return <Empty title={empty} />
  return (
    <>
      <div className="filters">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type">
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, model, location" aria-label="Search" />
      </div>
      <ul className="list rows">
        {shown.map((r) => (
          <li key={r.id}>
            <span>
              <Link to={`/inventory/${r.id}`}>
                <strong>{r.label}</strong>
              </Link>
              {r.product && <span className="muted"> — {r.product}</span>}
              <br />
              <span className="small">
                {r.state === 'INSTALLED' ? r.location.text : r.state_text}
                {r.readiness_text && r.state !== 'INSTALLED' && ` · ${r.readiness_text}`}
                {` · ${usageText(r.usage)} lifetime`}
                {r.storage_location && ` · ${r.storage_location}`}
              </span>
              <Compat rows={r.compatibility} />
            </span>
            {r.readiness === 'READY' && <Tag tone="good">ready</Tag>}
            {(r.readiness === 'NEEDS_PREPARATION' || r.readiness === 'NEEDS_REPAIR') && <Tag tone="warn">{r.readiness === 'NEEDS_REPAIR' ? 'repair' : 'prepare'}</Tag>}
            {r.readiness === 'WORN' && <Tag tone="bad">worn</Tag>}
          </li>
        ))}
      </ul>
    </>
  )
}

function StockTxnForm({ line, onDone }: { line: StockLine; onDone: (msg: string) => void }) {
  const [f, setF] = useState({ kind: 'PURCHASE', qty: '', packages: '', price: '', note: '', on: today() })
  const [err, setErr] = useState<string | null>(null)
  const [opId, setOpId] = useState(newOpId)
  async function save() {
    setErr(null)
    try {
      const qty = f.qty === '' ? null : Number(f.qty.replace(',', '.'))
      await api.post(`/consumables/${line.id}/txn`, { kind: f.kind, qty, on: f.on, note: f.note || null, packages: f.packages ? Number(f.packages) : null, cost_cents: f.price ? Math.round(Number(f.price.replace(',', '.')) * 100) : null }, opId)
      setOpId(newOpId())
      onDone({ PURCHASE: 'Purchase recorded.', RETURN: 'Return recorded.', ADJUST: 'Stock corrected.', USE: 'Use recorded.' }[f.kind] ?? 'Saved.')
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      <div className="chips">
        {[
          ['PURCHASE', 'Bought'],
          ['RETURN', 'Returned to shop'],
          ['ADJUST', 'Correct the count'],
          ...(line.tracking_mode === 'BULK' ? [['USE', 'Used']] : []),
        ].map(([k, l]) => (
          <button key={k} className={`chip ${f.kind === k ? 'chip-on' : ''}`} onClick={() => setF({ ...f, kind: k })}>
            {l}
          </button>
        ))}
      </div>
      <div className="row">
        <Field label={f.kind === 'ADJUST' ? `Change (+/− ${unitPlural(line.unit)})` : `Quantity (${unitPlural(line.unit)})`} hint={line.unit_note ?? undefined}>
          <input inputMode="decimal" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} placeholder={line.tracking_mode === 'BULK' ? 'optional' : ''} />
        </Field>
        {f.kind === 'PURCHASE' && line.tracking_mode === 'COUNTED' && (
          <Field label="Packages (optional)" hint="A pack of 2 links = 1 package, 2 links.">
            <input inputMode="numeric" value={f.packages} onChange={(e) => setF({ ...f, packages: e.target.value })} />
          </Field>
        )}
        {(f.kind === 'PURCHASE' || f.kind === 'RETURN') && (
          <Field label="Total € (optional)">
            <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />
          </Field>
        )}
      </div>
      <div className="row">
        <Field label="On">
          <input type="date" value={f.on} onChange={(e) => setF({ ...f, on: e.target.value })} />
        </Field>
        <Field label={f.kind === 'ADJUST' ? 'Why (required)' : 'Note (optional)'}>
          <input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder={f.kind === 'ADJUST' ? 'counted the drawer' : ''} />
        </Field>
      </div>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={save}>
          Save
        </button>
      </div>
    </div>
  )
}

function InstallFromStock({ line, onDone }: { line: StockLine; onDone: (msg: string) => void }) {
  const bikes = useApi<Bike[]>('/bikes')
  const { meta } = useApp()
  const ctype = meta.component_types.find((t) => t.code === line.component_type)
  const [f, setF] = useState({ bike: '', slot: ctype?.slots[0] ?? '', parent: '', at: today() })
  const setup = useApi<{ setup: { component_id: number; label: string; component_type: string }[] }>(f.bike && ctype?.parent_types.length ? `/bikes/${f.bike}` : null)
  const [err, setErr] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function save() {
    setErr(null)
    try {
      const r = await api.post<OpResult<{ label: string }>>(`/consumables/${line.id}/install`, { at: f.at, bike_id: f.parent ? null : Number(f.bike), parent_component_id: f.parent ? Number(f.parent) : null, slot: f.slot || null }, opId)
      onDone(`${r.result.label} installed from stock. ${r.change.notice}`)
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      <p className="small muted">One {line.unit} leaves the stock count and becomes an individual part with its own history.</p>
      <div className="row">
        <Field label="Bike">
          <select value={f.bike} onChange={(e) => setF({ ...f, bike: e.target.value, parent: '' })}>
            <option value="">Pick…</option>
            {bikes.data?.filter((b) => b.status === 'ACTIVE').map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
        {ctype && ctype.parent_types.length > 0 && (
          <Field label="Mounted on">
            <select value={f.parent} onChange={(e) => setF({ ...f, parent: e.target.value })}>
              <option value="">Pick…</option>
              {setup.data?.setup.filter((r) => ctype.parent_types.includes(r.component_type)).map((r) => (
                <option key={r.component_id} value={r.component_id}>
                  {r.label}
                </option>
              ))}
            </select>
          </Field>
        )}
        {ctype && ctype.slots.length > 1 && (
          <Field label="Position">
            <select value={f.slot} onChange={(e) => setF({ ...f, slot: e.target.value })}>
              {ctype.slots.map((s) => (
                <option key={s} value={s}>
                  {slotName(s)}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Installed on">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
      </div>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={!f.bike} onClick={save}>
          Install one
        </button>
      </div>
    </div>
  )
}

function AddStockForm({ mode, onDone }: { mode: 'COUNTED' | 'BULK'; onDone: (msg: string) => void }) {
  const { meta } = useApp()
  const [f, setF] = useState({ component_type: mode === 'COUNTED' ? 'INNER_TUBE' : '', maker: '', model: '', name: '', kind: 'WAX', unit: mode === 'BULK' ? 'ml' : '', qty: '', location: '', min: '', track: true })
  const [err, setErr] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function save() {
    setErr(null)
    try {
      let product_id: number | null = null
      if (f.component_type && f.model.trim()) {
        const p = await api.post<{ id: number }>('/products', { component_type: f.component_type, maker: f.maker || null, model: f.model })
        product_id = p.id
      }
      const body: Record<string, unknown> = { storage_location: f.location || null, min_stock: f.min ? Number(f.min) : null, name: f.name || null }
      if (mode === 'COUNTED') Object.assign(body, f.component_type ? { component_type: f.component_type, product_id } : { tracking_mode: 'COUNTED', kind: 'OTHER', unit: f.unit || 'pcs' })
      else Object.assign(body, { tracking_mode: 'BULK', kind: f.kind, unit: f.unit || 'ml', track_stock: f.track })
      const line = await api.post<{ id: number }>('/consumables', body, opId)
      // what is already on the shelf is a starting count, not a purchase (no price, no date of buying)
      if (f.qty) await api.post(`/consumables/${line.id}/txn`, { kind: 'ADJUST', qty: Number(f.qty.replace(',', '.')), on: today(), note: 'Starting stock' })
      onDone('Stock added.')
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      {mode === 'COUNTED' ? (
        <>
          <Field label="What" hint="Spare parts get their own history when installed. Pick 'Other' for patches or coin cells.">
            <select value={f.component_type} onChange={(e) => setF({ ...f, component_type: e.target.value })}>
              {meta.component_types.filter((t) => t.code !== 'OTHER').map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
              <option value="">Other counted item (patches, coin cells…)</option>
            </select>
          </Field>
          {f.component_type ? (
            <div className="row">
              <Field label="Maker (optional)">
                <input value={f.maker} onChange={(e) => setF({ ...f, maker: e.target.value })} />
              </Field>
              <Field label="Model (optional)">
                <input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} />
              </Field>
            </div>
          ) : (
            <div className="row">
              <Field label="Name">
                <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Park GP-2 patches" />
              </Field>
              <Field label="Unit">
                <input value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} placeholder="patch" />
              </Field>
            </div>
          )}
        </>
      ) : (
        <div className="row">
          <Field label="Kind">
            <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              {Object.entries(SUPPLY_KINDS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Product name">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Unit">
            <input value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
          </Field>
        </div>
      )}
      <div className="row">
        <Field label="In stock now (optional)">
          <input inputMode="decimal" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} />
        </Field>
        <Field label="Storage location (optional)">
          <input value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} placeholder="Workshop drawer" />
        </Field>
        <Field label="Minimum stock (optional)">
          <input inputMode="decimal" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} />
        </Field>
      </div>
      {mode === 'BULK' && (
        <label className="check">
          <input type="checkbox" checked={f.track} onChange={(e) => setF({ ...f, track: e.target.checked })} /> Track the amount in stock
        </label>
      )}
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={mode === 'BULK' ? !f.name : !f.component_type && !f.name} onClick={save}>
          Add
        </button>
      </div>
    </div>
  )
}

function StockLines({ lines, onChange, empty }: { lines: StockLine[]; onChange: (msg: string) => void; empty: string }) {
  const [sheet, setSheet] = useState<null | { txn: StockLine } | { install: StockLine }>(null)
  if (!lines.length) return <Empty title={empty} />
  return (
    <>
      <ul className="list rows">
        {lines.map((l) => (
          <li key={l.id}>
            <span>
              <strong>{l.name}</strong>
              <br />
              <span className="small">
                {l.stock ? (l.tracking_mode === 'COUNTED' ? plural(l.stock.qty, `new ${l.unit}`) : `${l.stock.qty.toLocaleString()} ${l.unit}${l.stock.known ? '' : ' (some uses not measured)'}`) : 'amount not tracked'}
                {l.individual_spares.length > 0 && ` + ${l.individual_spares.length} individual spare${l.individual_spares.length === 1 ? '' : 's'}`}
                {l.storage_location && ` · ${l.storage_location}`}
                {l.min_stock !== null && ` · Minimum: ${l.min_stock}`}
                {l.spent_cents ? ` · spent ${euro(l.spent_cents)}` : ''}
              </span>
              {l.unit_note && <span className="muted small"> · 1 {l.unit} = {l.unit_note}</span>}
              <Compat rows={l.compatibility} />
            </span>
            {l.low && <Tag tone="warn">below minimum</Tag>}
            <span className="row-actions">
              <button className="btn btn-small" onClick={() => setSheet({ txn: l })}>
                Stock change
              </button>
              {l.component_type && (l.stock?.qty ?? 0) >= 1 && (
                <button className="btn btn-small" onClick={() => setSheet({ install: l })}>
                  Install one
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {sheet && 'txn' in sheet && (
        <Sheet title={sheet.txn.name} onClose={() => setSheet(null)}>
          <StockTxnForm line={sheet.txn} onDone={(m) => { setSheet(null); onChange(m) }} />
        </Sheet>
      )}
      {sheet && 'install' in sheet && (
        <Sheet title={`Install from stock · ${sheet.install.name}`} onClose={() => setSheet(null)}>
          <InstallFromStock line={sheet.install} onDone={(m) => { setSheet(null); onChange(m) }} />
        </Sheet>
      )}
    </>
  )
}

function Sessions({ rows, onChange }: { rows: WorkSessionRow[]; onChange: (msg: string) => void }) {
  const [err, setErr] = useState<string | null>(null)
  async function undo(id: number) {
    const reason = window.prompt('Undo this whole entry? Stock, installations and the old part come back. Reason (optional):', '')
    if (reason === null) return
    setErr(null)
    try {
      const r = await api.post<OpResult<unknown>>(`/work-sessions/${id}/undo`, { reason: reason || null }, newOpId())
      onChange(`Undone. ${r.change.notice}`)
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  const meaningful = rows.filter((r) => r.transactions.length > 0)
  if (!meaningful.length) return <Empty title="No changes recorded yet" />
  return (
    <>
      <FormError error={err} form={false} />
      <ul className="list rows">
        {meaningful.map((w) => (
          <li key={w.id} className={w.undone_at ? 'excluded' : ''}>
            <span>
              <strong>{w.title ?? 'Work'}</strong> <span className="muted small">{when(w.performed_at)}</span>
              {w.cost_cents ? <span className="small"> · {euro(w.cost_cents)}</span> : null}
              <br />
              <span className="small">{w.transactions.map((t) => t.text).join(' · ')}</span>
              {w.undone_at && <span className="small"> · undone{w.undo_reason ? `: ${w.undo_reason}` : ''}</span>}
            </span>
            {!w.undone_at && (
              <button className="btn btn-small" onClick={() => undo(w.id)}>
                Undo
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

export default function InventoryPage() {
  const { toast } = useApp()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'available'
  const [sheet, setSheet] = useState<null | 'part' | 'stock' | 'supply' | 'json'>(null)
  const nav = useNavigate()
  const view = useApi<InventoryView>(['chains', 'all'].includes(tab) ? null : '/inventory')
  const parts = useApi<ComponentSummary[]>(tab === 'all' ? '/components' : null)
  const chains = useApi<ChainRow[]>(tab === 'chains' ? '/chains' : null)
  const changed = (msg: string) => {
    setSheet(null)
    toast(msg)
    view.reload()
  }
  const v = view.data
  return (
    <Card
      title="Inventory"
      actions={
        <>
          <button className="btn btn-primary" onClick={() => setSheet('part')}>
            Add part
          </button>
          <button className="btn" onClick={() => setSheet('json')}>
            Import JSON
          </button>
          <button className="btn" onClick={() => setSheet('stock')}>
            Add spare stock
          </button>
          <button className="btn" onClick={() => setSheet('supply')}>
            Add supply
          </button>
        </>
      }
    >
      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'tab-on' : ''}`} onClick={() => setParams({ tab: k })}>
            {l}
            {k === 'shopping' && v && v.shopping_list.length > 0 && <span className="count">{v.shopping_list.length}</span>}
            {k === 'service' && v && v.needs_service.length > 0 && <span className="count">{v.needs_service.length}</span>}
          </button>
        ))}
      </div>
      {!['chains', 'all'].includes(tab) && view.loading && !v && <Loading />}
      {!['chains', 'all'].includes(tab) && view.error && <ErrorBox error={view.error} onRetry={view.reload} />}
      {tab === 'available' && v && (
        <>
          <h3>Spare stock</h3>
          <StockLines lines={v.stock} onChange={changed} empty="No spare stock yet. Add tubes, pad sets or quick links as a count." />
          <h3>Individual spares</h3>
          <ItemList rows={v.available} empty="No individual spares. Parts you take off and store appear here with their history." />
        </>
      )}
      {tab === 'service' && v && <ItemList rows={v.needs_service} empty="Nothing waits for preparation or repair." />}
      {tab === 'installed' && v && <ItemList rows={v.installed} empty="Nothing installed yet." />}
      {tab === 'shopping' && v && (
        <>
          <p className="small muted">Suggestions only, from the minimum stock you set and the spares to keep (Settings). Nothing is ordered.</p>
          {v.shopping_list.length === 0 ? (
            <Empty title="Nothing below minimum">Set a minimum on a stock line to get reminders.</Empty>
          ) : (
            <ul className="list rows">
              {v.shopping_list.map((s) => (
                <li key={s.consumable_id ?? s.component_type}>
                  <span>
                    <strong>{s.name}</strong>
                    <br />
                    <span className="small">
                      Buy {plural(s.suggested_qty, s.unit)} · {s.available} available, minimum {s.min_stock}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {tab === 'history' && v && (
        <>
          <h3>Changes (can be undone)</h3>
          <Sessions rows={v.sessions} onChange={changed} />
          <h3>What happened to parts</h3>
          {v.history.length === 0 ? (
            <Empty title="No removed parts yet" />
          ) : (
            <ul className="list">
              {v.history.map((h, i) => (
                <li key={i} className={h.voided ? 'excluded' : ''}>
                  <span>{when(h.on)}</span>
                  <Link to={`/inventory/${h.component_id}`}>{h.label}</Link>
                  <span className="small">
                    {h.text}
                    {h.note ? ` · ${h.note}` : ''}
                    {h.voided ? ' · undone' : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {v.out_of_use.length > 0 && (
            <>
              <h3>Out of use (kept for history)</h3>
              <ItemList rows={v.out_of_use} empty="" />
            </>
          )}
        </>
      )}
      {tab === 'supplies' && v && (
        <>
          <p className="small muted">Bulk supplies: wax, sealant, fluid, grease. The amount used per job is optional.</p>
          <StockLines lines={v.supplies} onChange={changed} empty="No supplies yet." />
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
                <strong>
                  {c.label}
                  {c.mark && <span className="mark">{c.mark}</span>}
                </strong>
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
      {tab === 'all' && (
        <>
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
      {sheet === 'part' && (
        <Sheet title="Add part" onClose={() => setSheet(null)}>
          <ComponentForm presetType={tab === 'chains' ? 'CHAIN' : undefined} onSaved={(c) => nav(`/inventory/${c.id}`)} />
        </Sheet>
      )}
      {sheet === 'json' && (
        <Sheet title="Import products from JSON" onClose={() => setSheet(null)}>
          <ProductImport onDone={changed} />
        </Sheet>
      )}
      {sheet === 'stock' && (
        <Sheet title="Add spare stock" onClose={() => setSheet(null)}>
          <AddStockForm mode="COUNTED" onDone={changed} />
        </Sheet>
      )}
      {sheet === 'supply' && (
        <Sheet title="Add supply" onClose={() => setSheet(null)}>
          <AddStockForm mode="BULK" onDone={changed} />
        </Sheet>
      )}
    </Card>
  )
}

interface ComponentDetail extends ComponentSummary {
  ledger: { kind: string; date: string; km: number; ride_id?: number; ride_name?: string | null; bike?: string; slot?: string; basis?: string; counted: boolean; certain: boolean; is_estimate?: boolean; detail: string | null; running_km: number; state?: string }[]
  history: { id: number; where: string; slot: string; installed_at: string; removed_at: string | null; removal_reason: string | null; removal_outcome: string | null; voided: boolean; void_reason: string | null; km: number | null; note: string | null }[]
  service_status: Task[]
  rules: Rule[]
  events: EventRow[]
  actions: { code: string; name: string }[]
  specs: Record<string, unknown>
  dispositions: { id: number; disposition: string; label: string; effective_on: string; note: string | null; voided: boolean }[]
  inventory: ItemRow
  suggested_outcome: string
  parts: PartNode[]
  groupset_bike_id: number | null
  chain: (ChainRow & { cycles: { cycle: number; waxed_on: string; km: number; current: boolean }[] }) | null
  frame_history: FrameHistory | null
}

interface FrameHistory {
  inspections: EventRow[]
  crashes: { group: string; on: string; label: string; text: string | null; bike: string | null; ride_id: number | null; ride_label: string | null; open: boolean }[]
}

// A frame or fork keeps its own record: inspections and crashes from the bikes it was on, while it was on them.
function FrameHistoryCard({ h, kind }: { h: FrameHistory; kind: string }) {
  return (
    <Card title={`${kind} history`}>
      <p className="small muted">Inspections and crashes while this {kind.toLowerCase()} was on a bike. They stay with it when it moves to another build.</p>
      <details>
        <summary>
          Inspections ({h.inspections.length}){h.inspections[0] ? ` · last ${when(h.inspections[0].performed_on)}` : ''}
        </summary>
        {h.inspections.length === 0 ? (
          <p className="small muted">None recorded. Record one on the bike with "Record work done" → Frame and fork inspection.</p>
        ) : (
          <ul className="list">
            {h.inspections.map((e) => (
              <li key={e.id} className="small">
                {when(e.performed_on)} · {e.bike}
                {e.outcome ? ` · ${e.outcome}` : ''}
                {e.notes ? ` · ${e.notes}` : ''}
              </li>
            ))}
          </ul>
        )}
      </details>
      <details>
        <summary>Crashes ({h.crashes.length})</summary>
        {h.crashes.length === 0 ? (
          <p className="small muted">No crashes recorded.</p>
        ) : (
          <ul className="list">
            {h.crashes.map((c) => (
              <li key={c.group} className="small">
                {when(c.on)} · {c.bike}
                {c.ride_id ? (
                  <>
                    {' · '}
                    <Link to={`/rides?open=${c.ride_id}`}>{c.ride_label ?? 'ride'}</Link>
                  </>
                ) : null}
                {c.text ? ` · ${c.text}` : ''} {c.open ? <Tag tone="warn">open</Tag> : <Tag tone="good">solved</Tag>}
              </li>
            ))}
          </ul>
        )}
      </details>
    </Card>
  )
}

function RuleEditor({ rule, componentId, onDone }: { rule: Rule; componentId: number; onDone: () => void }) {
  const [f, setF] = useState({ interval_km: rule.interval_km?.toString() ?? '', interval_months: rule.interval_months?.toString() ?? '', interval_hours: rule.interval_hours?.toString() ?? '', interval_count: rule.interval_count?.toString() ?? '', window_min_km: rule.window_min_km?.toString() ?? '', window_max_km: rule.window_max_km?.toString() ?? '', origin: rule.origin === 'DEFAULT' ? 'PERSONAL' : rule.origin, scope: 'part' })
  const [err, setErr] = useState<string | null>(null)
  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  async function save(active = true) {
    setErr(null)
    const body: Record<string, unknown> = { origin: f.origin, active }
    if (rule.trigger === 'INTERVAL') Object.assign(body, { interval_km: num(f.interval_km), interval_months: num(f.interval_months), interval_hours: num(f.interval_hours) })
    else if (rule.trigger === 'PARENT_COUNT') Object.assign(body, { interval_count: num(f.interval_count) })
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
      {rule.notes && <p className="small muted">{rule.notes}</p>}
      {rule.trigger === 'INTERVAL' ? (
        <div className="row">
          <Field label="Every … km">
            <input inputMode="decimal" value={f.interval_km} onChange={(e) => setF({ ...f, interval_km: e.target.value })} />
          </Field>
          <Field label="or every … hours of riding">
            <input inputMode="decimal" aria-label="Every … hours of riding" value={f.interval_hours} onChange={(e) => setF({ ...f, interval_hours: e.target.value })} />
          </Field>
          <Field label="or every … months">
            <input inputMode="numeric" value={f.interval_months} onChange={(e) => setF({ ...f, interval_months: e.target.value })} />
          </Field>
        </div>
      ) : rule.trigger === 'PARENT_COUNT' ? (
        <div className="row">
          <Field label="Replace after it has been on … parts" hint="e.g. a quick link after 2 chains">
            <input inputMode="numeric" value={f.interval_count} onChange={(e) => setF({ ...f, interval_count: e.target.value })} />
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
  const [sheet, setSheet] = useState<null | 'log' | 'details' | 'start' | 'retire' | 'rule' | 'replace' | 'remove' | 'move' | 'disposition' | 'inuse' | { rule: Rule } | { correct: number }>(null)
  const [f, setF] = useState({ km: '', date: today(), estimate: true, reason: '', installed_at: '', removed_at: '', action_code: 'INSPECT', interval_km: '', interval_months: '', interval_hours: '', retire_as: '' })
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
  const installed = data.location.state === 'INSTALLED'
  const ctype = meta.component_types.find((t) => t.code === data.component_type)
  const canMove = !!ctype && (ctype.parent_types.length > 0 || ctype.slots.length > 1)
  const inv = data.inventory
  const changed = (c: Change) => {
    toast(c.notice)
    close()
    reload()
  }
  // Km the part already had (e.g. a wheelset used on other bikes). Defaults to the day it was first
  // installed here, so rides from then on count on top of the value.
  const firstInstall = data.history.filter((h) => !h.voided).map((h) => h.installed_at.slice(0, 10)).sort()[0]
  const openStart = () => {
    setF({ ...f, km: u.starting_km !== null ? String(u.starting_km) : '', date: (u.starting_effective ?? firstInstall ?? today()).slice(0, 10), estimate: u.starting_km !== null ? u.starting_is_estimate : true })
    setSheet('start')
  }
  return (
    <div className="grid">
      <Card
        className="span-2"
        title={
          <>
            {data.label} {data.mark && <span className="mark">{data.mark}</span>} <span className="muted small">{data.type_name}</span>
          </>
        }
        actions={
          data.status !== 'RETIRED' ? (
            <>
              {installed && (
                <button className="btn btn-primary" onClick={() => setSheet('replace')}>
                  Replace
                </button>
              )}
              <button className={installed ? 'btn' : 'btn btn-primary'} onClick={() => setSheet('log')} title="Cleaning, lubing, waxing, charging, checks, bleeds, repairs: anything you did to the bike or a part">
                Record work done
              </button>
              {installed && (
                <button className="btn" onClick={() => setSheet('remove')}>
                  Remove
                </button>
              )}
              {installed && canMove && (
                <button className="btn" onClick={() => setSheet('move')}>
                  Move
                </button>
              )}
              {ctype?.rider_gear && (
                <button className={data.disposition === 'IN_USE' ? 'btn' : 'btn btn-primary'} onClick={() => setSheet('inuse')}>
                  {data.disposition === 'IN_USE' ? 'Stop using' : 'Start using'}
                </button>
              )}
              {!installed && !ctype?.rider_gear && (
                <button className="btn" onClick={() => setSheet('disposition')}>
                  Change status
                </button>
              )}
              <button className="btn" onClick={() => setSheet('details')}>
                Edit details
              </button>
              <button className="btn" onClick={openStart}>
                Starting km
              </button>
              <button className="btn" onClick={() => setSheet('retire')}>
                Retire
              </button>
            </>
          ) : (
            data.disposition !== 'VOIDED' && (
              <button className="btn" onClick={() => setSheet('disposition')}>
                Back in stock…
              </button>
            )
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
            <span className="stat">{inv.state_text}</span>
            <span className="muted small">{installed ? data.location.text : [inv.readiness_text, data.storage_location].filter(Boolean).join(' · ')}</span>
          </div>
        </div>
        <p className="small">{u.summary}</p>
        {u.starting_km === null && data.status !== 'RETIRED' && (
          <p className="small muted">
            Already ridden before (on another bike or before Bike Log)?{' '}
            <button className="btn btn-small" onClick={openStart}>
              Add km from before
            </button>
          </p>
        )}
        {data.product && <p className="small muted">Product: {data.product}</p>}
        {(data.component_type === 'FRONT_WHEEL' || data.component_type === 'REAR_WHEEL') && (
          <p className="small">
            Tire setup: <TireSetupSelect wheelId={data.id} value={data.tire_setup} onSaved={reload} />{' '}
            <span className="muted">Set on the wheel, so it moves with the wheel; the tire on it follows.</span>
          </p>
        )}
        {(data.component_type === 'TIRE' || data.component_type === 'INNER_TUBE') && (
          <p className="small muted">
            Tire setup: {data.tire_setup_from ? `${setupLabel(meta.tire_setups, data.effective_tire_setup)} (set on ${data.tire_setup_from})` : 'follows the wheel it is mounted on'}
          </p>
        )}
        {data.component_type === 'TIRE' && (
          <p className="small">
            Tire pressure: <PressureNote tireId={data.id} value={data.pressure_note} onSaved={reload} />{' '}
            <span className="muted">A note, shown on the bike page. No reminder.</span>
          </p>
        )}
        {data.groupset_bike_id && (
          <p className="small">
            Part of the groupset of this bike: <Link to={`/bikes/${data.groupset_bike_id}/groupset`}>open the groupset page</Link>
          </p>
        )}
        <p className="small muted">
          {data.bundle ? (
            <>
              Bought in the bundle <strong>{data.bundle.name}</strong>
              {data.bundle.price_cents !== null ? ` (${euro(data.bundle.price_cents)}` : ' (no bundle price yet'}
              {data.bundle.merchant ? `, ${data.bundle.merchant}` : ''}
              {data.bundle.purchased_on ? `, ${when(data.bundle.purchased_on)}` : ''})
              {data.bundle.share_cents !== null ? ` · share ≈ ${euro(data.bundle.share_cents)} (estimate)` : ''}
            </>
          ) : (
            <>
              Price: {data.price_cents !== null ? euro(data.price_cents) : 'not entered'}
              {data.purchase_date ? ` · bought ${when(data.purchase_date)}` : ''}
            </>
          )}
          {data.serial_number ? ` · serial ${data.serial_number}` : ''}
          {data.warranty_until ? (
            <>
              {` · warranty until ${when(data.warranty_until)} `}
              {data.warranty_until < today() && <Tag>expired</Tag>}
            </>
          ) : (
            ''
          )}
        </p>
      </Card>
      {data.frame_history && <FrameHistoryCard h={data.frame_history} kind={data.type_name} />}
      {data.chain && <ChainCard comp={data} chain={data.chain} onChanged={reload} />}
      {data.parts.length > 0 && (
        <Card title="Parts on it" className="span-2">
          <p className="small muted">What is mounted on {data.label} now. Unfold a part to see what sits on it; open any part for its km, service and history.</p>
          <PartTree nodes={data.parts} />
        </Card>
      )}
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
                  {r.requires_setup && ` · only ${setupLabel(meta.tire_setups, r.requires_setup).toLowerCase()}`}
                </span>
                <button className="btn btn-small" onClick={() => setSheet({ rule: r })}>
                  Edit
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Journal componentId={data.id} className="span-2" />
      <ChangeLog componentId={data.id} refresh={data} className="span-2" />
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
                <span className="small">
                  {h.voided ? `void: ${h.void_reason}` : km(h.km)}
                  {!h.voided && h.removal_outcome && ` · ${h.removal_outcome === 'MOVED' ? 'moved' : (meta.dispositions.find((d) => d.code === h.removal_outcome)?.label ?? '').toLowerCase()}`}
                  {!h.voided && h.removal_reason && ` (${h.removal_reason})`}
                </span>
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
      {data.dispositions.length > 0 && (
        <Card title="What happened to it">
          <ul className="list">
            {data.dispositions.map((d) => (
              <li key={d.id} className={d.voided ? 'excluded' : ''}>
                <span>{when(d.effective_on)}</span>
                <span>{d.label}</span>
                <span className="small">
                  {d.note}
                  {d.voided ? ' · undone' : ''}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
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
        <Sheet title={`Record work done · ${data.label}`} onClose={close}>
          <LogMaintenance componentId={data.id} onDone={(msg) => { close(); toast(msg); reload() }} />
        </Sheet>
      )}
      {sheet === 'replace' && (
        <Sheet title={`Replace ${data.label}`} onClose={close}>
          <ReplaceForm componentId={data.id} onDone={(c, label) => { changed(c); toast(`${label} installed. ${c.notice}`) }} />
        </Sheet>
      )}
      {sheet === 'remove' && (
        <Sheet title={`Remove ${data.label}`} onClose={close}>
          <RemoveForm componentId={data.id} suggested={data.suggested_outcome} onDone={changed} />
        </Sheet>
      )}
      {sheet === 'move' && (
        <Sheet title={`Move ${data.label}`} onClose={close}>
          <MoveForm componentId={data.id} onDone={changed} />
        </Sheet>
      )}
      {sheet === 'inuse' && (
        <Sheet title={data.disposition === 'IN_USE' ? `Stop using ${data.label}` : `Start using ${data.label}`} onClose={close}>
          <InUseForm componentId={data.id} inUse={data.disposition === 'IN_USE'} onDone={(msg) => { close(); toast(msg); reload() }} />
        </Sheet>
      )}
      {sheet === 'disposition' && (
        <Sheet title={`Status of ${data.label}`} onClose={close}>
          <DispositionForm componentId={data.id} current={data.disposition} onDone={() => { close(); toast('Saved.'); reload() }} />
        </Sheet>
      )}
      {sheet === 'details' && (
        <Sheet title={`Edit ${data.label}`} onClose={close}>
          <DetailsForm comp={data} onDone={() => (close(), reload(), toast('Saved.'))} />
        </Sheet>
      )}
      {sheet === 'start' && (
        <Sheet title="Starting mileage" onClose={close}>
          <div className="form">
            <p className="small muted">
              The km the part already had on the given date, for example a wheelset used on other bikes. Rides recorded in Bike Log after that date are added on top; rides before it are treated as already inside this value. The date is set to the day the part was first installed here
              {firstInstall ? ` (${when(firstInstall)})` : ''}, so enter the km it had then.
            </p>
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
            <OutcomeChoice name="retire" outcomes={meta.dispositions.filter((d) => ['RETIRED', 'DISCARDED', 'SOLD'].includes(d.code))} value={f.retire_as || (data.suggested_outcome === 'DISCARDED' ? 'DISCARDED' : 'RETIRED')} suggested={data.suggested_outcome === 'DISCARDED' ? 'DISCARDED' : 'RETIRED'} onChange={(v) => setF({ ...f, retire_as: v })} />
            <Field label="Retired on">
              <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
            </Field>
            <Field label="Reason">
              <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="worn 0.5%" />
            </Field>
            <FormError error={err} />
            <div className="form-actions">
              <button className="btn btn-danger" onClick={() => plain(`/components/${data.id}/retire`, { on: f.date, reason: f.reason || null, disposition: f.retire_as || (data.suggested_outcome === 'DISCARDED' ? 'DISCARDED' : 'RETIRED') })}>
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
              <Field label="or every … hours of riding">
                <input inputMode="decimal" value={f.interval_hours} onChange={(e) => setF({ ...f, interval_hours: e.target.value })} />
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
                    interval_hours: f.interval_hours ? Number(f.interval_hours) : null,
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

// A chain's place in a rotation and its wax cycles (km ridden on each hot wax).
function ChainCard({ comp, chain, onChanged }: { comp: ComponentSummary; chain: NonNullable<ComponentDetail['chain']>; onChanged: () => void }) {
  const { toast } = useApp()
  const bikes = useApi<Bike[]>('/bikes')
  async function setRotation(v: string) {
    try {
      await api.patch(`/components/${comp.id}`, { rotation_bike_id: v ? Number(v) : null })
      toast(v ? `${comp.label} is in the chain rotation of ${bikes.data?.find((b) => b.id === Number(v))?.name}.` : `${comp.label} left the chain rotation.`)
      onChanged()
    } catch (e) {
      toast((e as Error).message)
    }
  }
  return (
    <Card title="Chain rotation and wax cycles" className="span-2">
      <p className="small">
        <ChainStateTag state={chain.state} /> {chain.text}
      </p>
      <label className="inline-field small">
        Chain rotation of{' '}
        <select aria-label="Chain rotation" value={chain.rotation_bike_id ?? ''} onChange={(e) => setRotation(e.target.value)}>
          <option value="">No rotation</option>
          {bikes.data?.filter((b) => b.status === 'ACTIVE').map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      {chain.rotation_bike_id && (
        <span className="small">
          {' '}
          · <Link to={`/bikes/${chain.rotation_bike_id}`}>open the bike for swaps and waxing</Link>
        </span>
      )}
      {chain.cycles.length === 0 ? (
        <p className="small muted">No hot wax recorded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Wax cycle</th>
              <th>Hot waxed</th>
              <th className="num">Km on that wax</th>
            </tr>
          </thead>
          <tbody>
            {[...chain.cycles].reverse().map((c) => (
              <tr key={c.cycle}>
                <td>{c.cycle}</td>
                <td>{when(c.waxed_on)}</td>
                <td className="num">
                  {km(c.km, 0)}
                  {c.current ? ' (current)' : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function DetailsForm({ comp, onDone }: { comp: ComponentSummary; onDone: () => void }) {
  const [f, setF] = useState({ label: comp.label, mark: comp.mark ?? '', price: centsInput(comp.price_cents), purchase_date: comp.purchase_date ?? '', serial_number: comp.serial_number ?? '', warranty_until: comp.warranty_until ?? '', notes: comp.notes ?? '' })
  const [err, setErr] = useState<string | null>(null)
  async function save() {
    setErr(null)
    const price = toCents(f.price)
    if (Number.isNaN(price)) return setErr('Price: enter an amount such as 49,90')
    try {
      await api.patch(`/components/${comp.id}`, { label: f.label, mark: f.mark || null, price_cents: price, purchase_date: f.purchase_date || null, serial_number: f.serial_number || null, warranty_until: f.warranty_until || null, notes: f.notes || null })
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      <Field label="Name / label">
        <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
      </Field>
      <div className="row">
        {comp.bundle ? (
          <Field label="Price paid" hint={`Bought in the bundle "${comp.bundle.name}": the bundle carries the price (change it on the bike page under "Bought as a bundle").`}>
            <input value="in bundle" disabled aria-label="Price paid (in bundle)" />
          </Field>
        ) : (
          <Field label="Price paid" hint="Leave empty if it came with the bike (then it is part of the bike's price).">
            <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="€" />
          </Field>
        )}
        <Field label="Bought on">
          <input type="date" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} />
        </Field>
      </div>
      <Field label="Mark" hint={comp.component_type === 'CHAIN' ? 'How you tell it apart from identical chains, e.g. "1 punch dot next to the quick link". Paint and nail polish come off in hot wax; a punch or engraver mark on an outer plate stays.' : 'How you tell it apart from identical parts (e.g. a dot, a sticker, a colour).'}>
        <input value={f.mark} maxLength={80} onChange={(e) => setF({ ...f, mark: e.target.value })} />
      </Field>
      <div className="row">
        <Field label="Serial number">
          <input value={f.serial_number} onChange={(e) => setF({ ...f, serial_number: e.target.value })} />
        </Field>
        <Field label="Warranty until">
          <input type="date" value={f.warranty_until} onChange={(e) => setF({ ...f, warranty_until: e.target.value })} />
        </Field>
      </div>
      <Field label="Notes" hint="For dated notes such as issues, use the journal below.">
        <textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      </Field>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={!f.label.trim()} onClick={save}>
          Save
        </button>
      </div>
    </div>
  )
}

// Shoes are worn, not mounted: while in use they (and the cleats on them) count every ride on any bike.
function InUseForm({ componentId, inUse, onDone }: { componentId: number; inUse: boolean; onDone: (msg: string) => void }) {
  const [on, setOn] = useState(today())
  const [error, setError] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function run() {
    setError(null)
    try {
      await api.post(`/components/${componentId}/disposition`, { disposition: inUse ? 'STORED' : 'IN_USE', on, note: null }, opId)
      onDone(inUse ? 'Stored: rides no longer count on these.' : 'In use: every ride from that day counts on these and the cleats on them.')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="form">
      <p className="muted">
        {inUse
          ? 'Rides after this day no longer count on these shoes and their cleats.'
          : 'From this day every ride with a bike counts on these shoes and the cleats mounted on them, whichever bike you ride.'}
      </p>
      <Field label={inUse ? 'Stopped on' : 'In use since'}>
        <input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
      </Field>
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={run}>
          {inUse ? 'Stop using' : 'Start using'}
        </button>
      </div>
    </div>
  )
}
