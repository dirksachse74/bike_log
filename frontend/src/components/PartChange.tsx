// Replace, remove, move and "what happened to it" forms. Each one asks for the effective date and
// keeps what was typed after a recoverable error. The server records each step as its own
// transaction inside one work session, which the Inventory history can undo as a whole.
import { useEffect, useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { today, usageText } from '../format'
import { useApi } from '../hooks'
import type { Change, OpResult } from '../types'
import { ChangeNotice, Empty, ErrorBox, Field, FormError, Loading, Tag } from './ui'

export interface Disposition {
  code: string
  label: string
}

interface SpareRow {
  id: number
  label: string
  product: string | null
  state_text: string
  readiness: string | null
  readiness_text: string | null
  usage: { total_km: number } & Parameters<typeof usageText>[0]
  storage_location: string | null
  fit: 'VERIFIED' | 'UNVERIFIED' | 'SAME_PRODUCT' | 'UNKNOWN'
}

interface StockRow {
  id: number
  name: string
  unit: string
  unit_note: string | null
  stock: { qty: number } | null
  storage_location: string | null
  fit: SpareRow['fit']
}

interface ReplaceOptions {
  component: { id: number; label: string; type_name: string; component_type: string; product: string | null; product_id: number | null }
  location: { text: string; slot?: string; bike?: string | null }
  suggested_outcome: string
  outcomes: Disposition[]
  spares: SpareRow[]
  stock: StockRow[]
  children: { component_id: number; label: string; type_name: string; slot: string; carry_over: boolean; note: string | null }[]
}

const FIT_TEXT: Record<SpareRow['fit'], [string, 'good' | 'info' | 'warn' | 'neutral']> = {
  VERIFIED: ['verified fit for this bike', 'good'],
  UNVERIFIED: ['listed for this bike, not verified', 'warn'],
  SAME_PRODUCT: ['same product as the old part', 'info'],
  UNKNOWN: ['compatibility not recorded', 'neutral'],
}

export function FitTag({ fit }: { fit: SpareRow['fit'] }) {
  const [text, tone] = FIT_TEXT[fit]
  return <Tag tone={tone}>{text}</Tag>
}

export function OutcomeChoice({ outcomes, value, suggested, onChange, name }: { outcomes: Disposition[]; value: string; suggested: string; onChange: (v: string) => void; name: string }) {
  return (
    <fieldset className="field">
      <legend className="field-label">What happened to the old item?</legend>
      <div className="chips">
        {outcomes.map((o) => (
          <label key={o.code} className={`chip ${value === o.code ? 'chip-on' : ''}`}>
            <input type="radio" name={name} value={o.code} checked={value === o.code} onChange={() => onChange(o.code)} className="sr-only" />
            {o.label}
            {o.code === suggested && <span className="muted small"> · suggested</span>}
          </label>
        ))}
      </div>
      <span className="field-hint">Its record, mileage and history are always kept, also when discarded.</span>
    </fieldset>
  )
}

type Source = { kind: 'spare'; id: number } | { kind: 'stock'; id: number } | { kind: 'same' } | { kind: 'new' }

export function ReplaceForm({ componentId, onDone }: { componentId: number; onDone: (c: Change, label: string) => void }) {
  const opts = useApi<ReplaceOptions>(`/components/${componentId}/replace-options`)
  const products = useApi<{ id: number; maker: string | null; model: string }[]>(opts.data ? `/products?component_type=${opts.data.component.component_type}` : null)
  const [source, setSource] = useState<Source | null>(null)
  const [f, setF] = useState({ at: today(), reason: '', outcome: '', label: '', product_id: '', price: '' })
  const [preview, setPreview] = useState<Change | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const [carry, setCarry] = useState<Set<number> | null>(null)
  useEffect(() => {
    const d = opts.data
    if (!d) return
    setCarry((c) => c ?? new Set(d.children.filter((x) => x.carry_over).map((x) => x.component_id)))
    setF((x) => (x.outcome ? x : { ...x, outcome: d.suggested_outcome }))
    setSource((s) => s ?? (d.stock[0] ? { kind: 'stock', id: d.stock[0].id } : d.spares[0] ? { kind: 'spare', id: d.spares[0].id } : { kind: 'same' }))
  }, [opts.data])
  if (opts.loading && !opts.data) return <Loading />
  if (opts.error) return <ErrorBox error={opts.error} onRetry={opts.reload} />
  const d = opts.data
  if (!d || !source) return null
  const body = () => {
    const b: Record<string, unknown> = { at: f.at, reason: f.reason || null, old_outcome: f.outcome, carry_over: [...(carry ?? [])] }
    if (source.kind === 'spare') b.new_component_id = source.id
    if (source.kind === 'stock') b.from_stock_id = source.id
    if (source.kind === 'same') b.same_product = true
    if (source.kind === 'new') b.new = { label: f.label || null, product_id: f.product_id ? Number(f.product_id) : null, price_cents: f.price ? Math.round(Number(f.price.replace(',', '.')) * 100) : null }
    return b
  }
  async function run(dry: boolean) {
    setError(null)
    setBusy(true)
    try {
      const r = await api.post<OpResult<{ new_label: string }>>(`/components/${componentId}/replace${dry ? '?dry_run=true' : ''}`, body(), dry ? undefined : opId)
      if (dry) setPreview(r.change)
      else onDone(r.change, r.result.new_label)
    } catch (e) {
      setError((e as Error).message)
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }
  const is = (k: Source['kind'], id?: number) => source.kind === k && (id === undefined || ('id' in source && source.id === id))
  return (
    <div className="form">
      <p className="small">
        Outgoing: <strong>{d.component.label}</strong> {d.component.product && <span className="muted">({d.component.product})</span>} · {d.location.text}
      </p>
      <fieldset className="field">
        <legend className="field-label">Install instead</legend>
        <div className="pick-list">
          {d.stock.map((s) => (
            <label key={`s${s.id}`} className={`pick ${is('stock', s.id) ? 'pick-on' : ''}`}>
              <input type="radio" name="src" checked={is('stock', s.id)} onChange={() => setSource({ kind: 'stock', id: s.id })} />
              <span>
                <strong>One from stock: {s.name}</strong>
                <span className="small muted">
                  {' '}
                  {s.stock?.qty ?? 0} {s.unit}
                  {(s.stock?.qty ?? 0) === 1 ? '' : 's'} left{s.storage_location ? ` · ${s.storage_location}` : ''}
                </span>
                <br />
                <FitTag fit={s.fit} />
              </span>
            </label>
          ))}
          {d.spares.map((s) => (
            <label key={`c${s.id}`} className={`pick ${is('spare', s.id) ? 'pick-on' : ''}`}>
              <input type="radio" name="src" checked={is('spare', s.id)} onChange={() => setSource({ kind: 'spare', id: s.id })} />
              <span>
                <strong>{s.label}</strong> <span className="small muted">{s.product ?? ''}</span>
                <br />
                <span className="small">
                  {s.state_text} · {s.readiness_text} · {usageText(s.usage)} lifetime
                </span>{' '}
                <FitTag fit={s.fit} />
                {s.readiness !== 'READY' && <Tag tone="warn">not ready</Tag>}
              </span>
            </label>
          ))}
          <label className={`pick ${is('same') ? 'pick-on' : ''}`}>
            <input type="radio" name="src" checked={is('same')} onChange={() => setSource({ kind: 'same' })} />
            <span>
              <strong>New item, same product</strong>
              <span className="small muted"> · a new physical part{d.component.product ? ` (${d.component.product})` : ''}</span>
            </span>
          </label>
          <label className={`pick ${is('new') ? 'pick-on' : ''}`}>
            <input type="radio" name="src" checked={is('new')} onChange={() => setSource({ kind: 'new' })} />
            <span>
              <strong>Newly bought item</strong>
              <span className="small muted"> · name, product and price are optional</span>
            </span>
          </label>
        </div>
      </fieldset>
      {source.kind === 'new' && (
        <div className="row">
          <Field label="Name (optional)">
            <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder={`${d.component.label} (2)`} />
          </Field>
          <Field label="Product (optional)">
            <select value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}>
              <option value="">Not recorded</option>
              {products.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {[p.maker, p.model].filter(Boolean).join(' ')}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Price € (optional)">
            <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />
          </Field>
        </div>
      )}
      <div className="row">
        <Field label="Installed on">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
        <Field label="Removal reason (optional)">
          <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="puncture, worn, rotation…" />
        </Field>
      </div>
      <OutcomeChoice name="replace-outcome" outcomes={d.outcomes} value={f.outcome} suggested={d.suggested_outcome} onChange={(v) => setF({ ...f, outcome: v })} />
      {d.children.length > 0 && (
        <fieldset className="field">
          <legend className="field-label">Parts on {d.component.label}: move them to the new one?</legend>
          {d.children.map((c) => (
            <label key={c.component_id} className="check">
              <input
                type="checkbox"
                aria-label={`Move ${c.label} to the new part`}
                checked={carry?.has(c.component_id) ?? false}
                onChange={(e) => {
                  const next = new Set(carry ?? [])
                  if (e.target.checked) next.add(c.component_id)
                  else next.delete(c.component_id)
                  setCarry(next)
                }}
              />{' '}
              {c.label} <span className="small muted">({c.type_name}){c.note ? ` · ${c.note}` : ''}</span>
            </label>
          ))}
          <p className="small muted">Ticked parts move over and keep their own km. Unticked parts stay with the old part.</p>
        </fieldset>
      )}
      <ChangeNotice change={preview} />
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn" disabled={busy} onClick={() => run(true)}>
          Preview
        </button>
        <button className="btn btn-primary" disabled={busy} onClick={() => run(false)}>
          Replace
        </button>
      </div>
    </div>
  )
}

export function RemoveForm({ componentId, suggested, onDone }: { componentId: number; suggested: string; onDone: (c: Change) => void }) {
  const { meta } = useApp()
  const [f, setF] = useState({ at: today(), reason: '', outcome: suggested === 'DISCARDED' ? 'DISCARDED' : 'STORED' })
  const [preview, setPreview] = useState<Change | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function run(dry: boolean) {
    setError(null)
    try {
      const r = await api.post<OpResult<unknown>>(`/components/${componentId}/remove${dry ? '?dry_run=true' : ''}`, { at: f.at, reason: f.reason || null, outcome: f.outcome }, dry ? undefined : opId)
      if (dry) setPreview(r.change)
      else onDone(r.change)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="form">
      <div className="row">
        <Field label="Removed on">
          <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
        <Field label="Reason (optional)">
          <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
        </Field>
      </div>
      <OutcomeChoice name="remove-outcome" outcomes={meta.dispositions} value={f.outcome} suggested={suggested} onChange={(v) => setF({ ...f, outcome: v })} />
      <ChangeNotice change={preview} />
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn" onClick={() => run(true)}>
          Preview
        </button>
        <button className="btn btn-primary" onClick={() => run(false)}>
          Remove
        </button>
      </div>
    </div>
  )
}

interface MoveTarget {
  parent_component_id: number | null
  bike_id: number | null
  slot: string
  text: string
  occupied_by: string | null
}

export function MoveForm({ componentId, onDone }: { componentId: number; onDone: (c: Change) => void }) {
  const targets = useApi<MoveTarget[]>(`/components/${componentId}/move-targets`)
  const [pick, setPick] = useState(0)
  const [at, setAt] = useState(today())
  const [error, setError] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  if (targets.loading && !targets.data) return <Loading />
  if (targets.error) return <ErrorBox error={targets.error} onRetry={targets.reload} />
  if (!targets.data?.length) return <Empty title="No other position on this bike">Use Replace or Remove instead.</Empty>
  const t = targets.data[pick]
  async function run() {
    setError(null)
    try {
      const r = await api.post<OpResult<unknown>>(`/components/${componentId}/move`, { at, bike_id: t.bike_id, parent_component_id: t.parent_component_id, slot: t.slot, swap: !!t.occupied_by }, opId)
      onDone(r.change)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="form">
      <p className="small muted">A position change keeps the part's identity and its kilometres.</p>
      <Field label="Move to">
        <select value={pick} onChange={(e) => setPick(Number(e.target.value))}>
          {targets.data.map((x, i) => (
            <option key={i} value={i}>
              {x.text}
              {x.occupied_by ? ` (swap with ${x.occupied_by})` : ''}
            </option>
          ))}
        </select>
      </Field>
      <Field label="On">
        <input type="date" value={at} onChange={(e) => setAt(e.target.value)} />
      </Field>
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={run}>
          {t.occupied_by ? 'Swap positions' : 'Move'}
        </button>
      </div>
    </div>
  )
}

export function DispositionForm({ componentId, current, onDone }: { componentId: number; current: string; onDone: () => void }) {
  const { meta } = useApp()
  const [f, setF] = useState({ on: today(), disposition: current === 'STORED' ? 'AWAITING_SERVICE' : 'STORED', note: '' })
  const [error, setError] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  async function run() {
    setError(null)
    try {
      await api.post(`/components/${componentId}/disposition`, f, opId)
      onDone()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <div className="form">
      <OutcomeChoice name="disp" outcomes={meta.dispositions} value={f.disposition} suggested={current} onChange={(v) => setF({ ...f, disposition: v })} />
      <div className="row">
        <Field label="On">
          <input type="date" value={f.on} onChange={(e) => setF({ ...f, on: e.target.value })} />
        </Field>
        <Field label="Note (optional)">
          <input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        </Field>
      </div>
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={run}>
          Save
        </button>
      </div>
    </div>
  )
}

