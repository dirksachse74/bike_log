import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { today, when } from '../format'
import { useApi } from '../hooks'
import type { SpokeBreak, SpokeInfo } from '../types'
import { Field, FormError, Tag } from './ui'

// Broken spokes on a wheel (DECISIONS 109): when each one broke and when it was replaced. After the limit
// (Settings, default 3) since the wheel was laced, the wheel shows "replace the wheel (or re-lace it)".

interface StockLine {
  id: number
  name: string
  unit: string
  component_type: string | null
  tracking_mode: string
  stock: { qty: number } | null
}

function spokeTone(sp: SpokeInfo): 'bad' | 'warn' | 'neutral' {
  return sp.broken >= sp.relace_after || sp.open > 0 ? 'bad' : sp.broken === sp.relace_after - 1 ? 'warn' : 'neutral'
}

export function SpokeCount({ sp }: { sp: SpokeInfo }) {
  return (
    <>
      <Tag tone={spokeTone(sp)}>
        {sp.broken} of {sp.relace_after} broken spokes{sp.since ? ` since ${when(sp.since)}` : ''}
      </Tag>
      {sp.open > 0 && <Tag tone="bad">{sp.open} not replaced yet</Tag>}
      {sp.broken >= sp.relace_after && <Tag tone="bad">Replace the wheel (or re-lace it)</Tag>}
    </>
  )
}

function SpokeSource({ value, onChange, lines }: { value: string; onChange: (v: string) => void; lines: StockLine[] }) {
  return (
    <Field label="New spoke from" hint={lines.length ? undefined : 'Spare spokes kept at home go under Inventory → Add spare stock (type Spokes).'}>
      <select aria-label="New spoke from" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Not from my stock (shop, other)</option>
        {lines.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name} ({l.stock?.qty ?? 0} {l.unit} at home)
          </option>
        ))}
      </select>
    </Field>
  )
}

// Log a broken spoke, mark one replaced later, see (and correct) the wheel's history.
export function BrokenSpokes({ wheelId, info, onChange }: { wheelId: number; info: SpokeInfo; onChange: () => void }) {
  const { toast } = useApp()
  const consumables = useApi<StockLine[]>('/consumables')
  const lines = (consumables.data ?? []).filter((l) => l.component_type === 'SPOKES' && l.tracking_mode === 'COUNTED' && (l.stock?.qty ?? 0) >= 1)
  const [f, setF] = useState({ broke_on: today(), replaced: 'no', replaced_on: today(), source: '', note: '' })
  const [later, setLater] = useState<{ group: string; on: string; source: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId, setOpId] = useState(newOpId)
  async function run(fn: () => Promise<unknown>, msg: string) {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      toast(msg)
      setOpId(newOpId())
      setLater(null)
      onChange()
      consumables.reload()
      return true
    } catch (e) {
      setErr((e as Error).message)
      return false
    } finally {
      setBusy(false)
    }
  }
  async function save() {
    const replaced = f.replaced === 'yes'
    const n = info.broken + 1
    const ok = await run(
      () =>
        api.post(
          `/components/${wheelId}/broken-spokes`,
          { broke_on: f.broke_on, replaced_on: replaced ? f.replaced_on : null, stock_line_id: replaced && f.source ? Number(f.source) : null, note: f.note || null },
          opId,
        ),
      `Broken spoke logged (${n} of ${info.relace_after})${replaced ? ', replaced' : ', not replaced yet'}.${n >= info.relace_after ? ' Time to replace the wheel (or re-lace it).' : ''}`,
    )
    if (ok) setF({ ...f, note: '', source: '' })
  }
  return (
    <div className="form broken-spokes">
      <p className="small">
        <SpokeCount sp={info} />
      </p>
      <h3>Log a broken spoke</h3>
      <div className="row">
        <Field label="Broke on">
          <input type="date" aria-label="Broke on" value={f.broke_on} onChange={(e) => setF({ ...f, broke_on: e.target.value })} />
        </Field>
        <Field label="Replaced?">
          <select aria-label="Replaced?" value={f.replaced} onChange={(e) => setF({ ...f, replaced: e.target.value })}>
            <option value="no">Not yet</option>
            <option value="yes">Yes</option>
          </select>
        </Field>
        {f.replaced === 'yes' && (
          <Field label="Replaced on">
            <input type="date" aria-label="Replaced on" value={f.replaced_on} min={f.broke_on} onChange={(e) => setF({ ...f, replaced_on: e.target.value })} />
          </Field>
        )}
      </div>
      {f.replaced === 'yes' && <SpokeSource value={f.source} onChange={(v) => setF({ ...f, source: v })} lines={lines} />}
      <Field label="Note (optional)">
        <input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="e.g. drive side, on the cobbles" />
      </Field>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !f.broke_on} onClick={save}>
          Save broken spoke
        </button>
      </div>
      <details className="spoke-history" open={info.breaks.length > 0}>
        <summary>
          <strong>Broken spokes on this wheel</strong> <span className="muted small">({info.breaks.length})</span>
        </summary>
        {info.breaks.length === 0 && <p className="small muted">None so far.</p>}
        <ul className="list rows">
          {info.breaks.map((b: SpokeBreak, i) => (
            <li key={b.group ?? `e${b.event_id ?? i}`} data-broke={b.broke_on}>
              <span>
                Broke {when(b.broke_on)} ·{' '}
                {b.replaced_on ? (
                  <>replaced {when(b.replaced_on)}</>
                ) : b.repair ? (
                  <>{b.repair_text ?? 'repaired'}</>
                ) : (
                  <strong>not replaced yet</strong>
                )}
                {b.note && <span className="muted"> · {b.note}</span>}
                {b.ride_id && (
                  <>
                    {' '}
                    · <Link to={`/rides?open=${b.ride_id}`}>ride</Link>
                  </>
                )}
                {!b.counted && <span className="muted"> · before the last re-lace</span>}
              </span>
              {b.group && (
                <span className="row-actions">
                  {!b.repair && (
                    <button className="btn btn-small" onClick={() => setLater({ group: b.group!, on: today(), source: '' })}>
                      Mark replaced
                    </button>
                  )}
                  <button className="btn btn-small" disabled={busy} onClick={() => window.confirm('Remove this broken spoke? (Logged by mistake. A spoke taken from stock goes back.)') && run(() => api.post(`/components/${wheelId}/broken-spokes/${b.group}/remove`, {}), 'Broken spoke removed.')}>
                    Remove
                  </button>
                </span>
              )}
              {later?.group === b.group && (
                <div className="form spoke-later">
                  <div className="row">
                    <Field label="Replaced on">
                      <input type="date" aria-label="Replaced on (later)" value={later.on} min={b.broke_on} onChange={(e) => setLater({ ...later, on: e.target.value })} />
                    </Field>
                    <SpokeSource value={later.source} onChange={(v) => setLater({ ...later, source: v })} lines={lines} />
                  </div>
                  <div className="form-actions">
                    <button className="btn btn-primary btn-small" disabled={busy || !later.on} onClick={() => run(() => api.post(`/components/${wheelId}/broken-spokes/${b.group}/replaced`, { replaced_on: later.on, stock_line_id: later.source ? Number(later.source) : null }, opId), 'Spoke marked as replaced.')}>
                      Save
                    </button>
                    <button className="btn btn-small" onClick={() => setLater(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
        <p className="small muted">A new wheel, a re-lace or a new spoke set starts the count again; older breaks stay in the list. The limit is under Settings.</p>
      </details>
    </div>
  )
}
