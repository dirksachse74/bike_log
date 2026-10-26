// Fixing an incident: for each damaged part, Replaced (a spare, one from stock or a new one), Patched /
// Repaired, or Nothing yet. On the road the fix takes the ride date, at home today's date. Every fix is a
// work session, so "Undo fix" (or Inventory → History) takes it back. Also "Swap tube" for a wheel.
import { useEffect, useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { today, when } from '../format'
import { useApi } from '../hooks'
import type { FixOptions, FixPartOption, FixSourceOptions } from '../types'
import { ReplaceForm } from './PartChange'
import { Empty, ErrorBox, Field, FormError, Loading } from './ui'

type Source = { kind: 'stock' | 'spare'; id: number } | { kind: 'same' | 'new' }
type PartFix = { action: 'NONE' | 'REPLACED' | 'REPAIRED'; source: Source | null; old_outcome: string }

const srcKey = (s: Source | null) => (s ? `${s.kind}${'id' in s ? s.id : ''}` : '')

function defaultSource(o: FixSourceOptions | null): Source | null {
  if (!o) return null
  if (o.stock[0]) return { kind: 'stock', id: o.stock[0].id }
  if (o.spares[0]) return { kind: 'spare', id: o.spares[0].id }
  return { kind: 'new' }
}

// Where the new tube or tire comes from: stock, a stored spare, or a new one.
function SourcePick({ name, options, isPart, value, onChange }: { name: string; options: FixSourceOptions; isPart: boolean; value: Source | null; onChange: (s: Source) => void }) {
  const picks: [Source, string, string][] = [
    ...options.stock.map((s): [Source, string, string] => [{ kind: 'stock', id: s.id }, `One from stock: ${s.name}`, `${s.qty} ${s.unit}${s.qty === 1 ? '' : 's'} left`]),
    ...options.spares.map((s): [Source, string, string] => [{ kind: 'spare', id: s.id }, s.label, 'stored spare']),
    ...(isPart ? [[{ kind: 'same' }, 'New item, same product', 'a new physical part'] as [Source, string, string]] : []),
    [{ kind: 'new' }, isPart || options.tracks_new ? 'Newly bought item' : 'A new one', isPart || options.tracks_new ? 'tracked from now on' : 'not taken from stock, not tracked'],
  ]
  return (
    <div className="pick-list">
      {picks.map(([s, label, hint]) => (
        <label key={srcKey(s)} className={`pick ${srcKey(value) === srcKey(s) ? 'pick-on' : ''}`}>
          <input type="radio" name={name} checked={srcKey(value) === srcKey(s)} onChange={() => onChange(s)} />
          <span>
            <strong>{label}</strong> <span className="small muted">· {hint}</span>
          </span>
        </label>
      ))}
    </div>
  )
}

export function FixForm({ group, onDone, onCancel }: { group: string; onDone: () => void; onCancel: () => void }) {
  const { toast } = useApp()
  const opts = useApi<FixOptions>(`/incidents/${group}/fix-options`)
  const [where, setWhere] = useState<'road' | 'home' | 'other'>('road')
  const [other, setOther] = useState(today())
  const [fixes, setFixes] = useState<Record<number, PartFix>>({})
  const [note, setNote] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  useEffect(() => {
    const d = opts.data
    if (!d) return
    setFixes((f) => {
      if (Object.keys(f).length) return f
      const init: Record<number, PartFix> = {}
      for (const p of d.parts) if (!p.repair) init[p.entry_id] = { action: 'NONE', source: defaultSource(p.options), old_outcome: p.options?.suggested_outcome ?? '' }
      return init
    })
  }, [opts.data])
  if (opts.loading && !opts.data) return <Loading />
  if (opts.error) return <ErrorBox error={opts.error} onRetry={opts.reload} />
  const d = opts.data
  if (!d) return null
  const at = where === 'road' ? d.ride_date : where === 'home' ? today() : other
  const set = (p: FixPartOption, x: Partial<PartFix>) => setFixes({ ...fixes, [p.entry_id]: { ...fixes[p.entry_id], ...x } })
  async function save() {
    setErr(null)
    setBusy(true)
    try {
      const parts = Object.entries(fixes).map(([id, f]) => ({
        entry_id: Number(id),
        action: f.action,
        source: f.action === 'REPLACED' ? f.source : null,
        old_outcome: f.old_outcome || null,
      }))
      const r = await api.post<{ solved: boolean; texts: string[] }>(`/incidents/${group}/fix`, { at, parts, note: note || null }, opId)
      toast(`${r.texts.join('; ')}.${r.solved ? ' Incident solved.' : ' The incident stays open for the rest.'}`)
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const todo = d.parts.filter((p) => !p.repair)
  return (
    <div className="form fix-form">
      <fieldset className="field">
        <legend className="field-label">When</legend>
        <div className="chips">
          {(
            [
              ['road', `On the road (${when(d.ride_date)})`],
              ['home', 'At home (today)'],
              ['other', 'Another day'],
            ] as const
          ).map(([k, label]) => (
            <label key={k} className={`chip ${where === k ? 'chip-on' : ''}`}>
              <input type="radio" className="sr-only" name={`fix-when-${group}`} checked={where === k} onChange={() => setWhere(k)} />
              {label}
            </label>
          ))}
        </div>
        {where === 'other' && <input type="date" aria-label="Fix date" value={other} min={d.ride_date} onChange={(e) => setOther(e.target.value)} />}
      </fieldset>
      {d.parts
        .filter((p) => p.repair)
        .map((p) => (
          <p key={p.entry_id} className="small">
            ✓ <strong>{p.label}</strong>: {p.repair_text}
          </p>
        ))}
      {todo.length === 0 && <Empty title="Everything in this incident is fixed already" />}
      {todo.map((p) => {
        const f = fixes[p.entry_id]
        if (!f) return null
        const actions: [PartFix['action'], string][] = [
          ...(p.options?.replace ? [['REPLACED', 'Replaced'] as [PartFix['action'], string]] : []),
          ['REPAIRED', p.repair_label ?? 'Repaired'],
          ['NONE', 'Nothing yet'],
        ]
        return (
          <fieldset key={p.entry_id} className="field fix-part">
            <legend className="field-label">{p.label}</legend>
            <div className="chips" role="radiogroup" aria-label={`Fix ${p.label}`}>
              {actions.map(([a, label]) => (
                <label key={a} className={`chip ${f.action === a ? 'chip-on' : ''}`}>
                  <input type="radio" className="sr-only" name={`fix-${p.entry_id}`} checked={f.action === a} onChange={() => set(p, { action: a })} />
                  {label}
                </label>
              ))}
            </div>
            {f.action === 'REPLACED' && p.options && p.kind !== 'OTHER' && (
              <>
                <SourcePick name={`src-${p.entry_id}`} options={p.options} isPart={p.kind === 'PART'} value={f.source} onChange={(s) => set(p, { source: s })} />
                {p.kind === 'POSITION' && p.damage === 'TIRE' && !p.options.wheel_label && <p className="small muted">No wheel recorded at this position, so stored spares cannot be put on it here.</p>}
                {p.kind === 'PART' && p.options.outcomes && (
                  <Field label={`What happened to ${p.label}?`}>
                    <select value={f.old_outcome} onChange={(e) => set(p, { old_outcome: e.target.value })}>
                      {p.options.outcomes.map((o) => (
                        <option key={o.code} value={o.code}>
                          {o.label}
                          {o.code === p.options?.suggested_outcome ? ' (suggested)' : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </>
            )}
          </fieldset>
        )
      })}
      {todo.length > 0 && (
        <Field label="Note (optional)">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. glass shard still in the tire" />
        </Field>
      )}
      <p className="small muted">The old part keeps its km. When every part is fixed, the incident is solved; otherwise it stays open in Upcoming tasks.</p>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
        {todo.length > 0 && (
          <button className="btn btn-primary" disabled={busy} onClick={save}>
            {busy ? 'Saving…' : 'Save fix'}
          </button>
        )}
      </div>
    </div>
  )
}

// Manage parts → Swap tube: a tube tracked as a part is replaced the usual way; an untracked tube is
// taken from stock (or a new one), so the spare count drops.
export function SwapTube({ bikeId, onDone }: { bikeId: number; onDone: (text: string) => void }) {
  const [wheel, setWheel] = useState<'FRONT_WHEEL' | 'REAR_WHEEL'>('REAR_WHEEL')
  const opts = useApi<FixSourceOptions>(`/bikes/${bikeId}/position-options?wheel=${wheel}&damage=TUBE`)
  const [source, setSource] = useState<Source | null>(null)
  const [at, setAt] = useState(today())
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  useEffect(() => {
    if (opts.data) setSource(defaultSource({ ...opts.data, replace: true }))
  }, [opts.data])
  async function save() {
    setErr(null)
    setBusy(true)
    try {
      const r = await api.post<{ text: string }>(`/bikes/${bikeId}/swap-position`, { wheel, damage: 'TUBE', at, source }, opId)
      onDone(r.text)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="form">
      <div className="chips" role="radiogroup" aria-label="Which wheel">
        {(
          [
            ['FRONT_WHEEL', 'Front wheel'],
            ['REAR_WHEEL', 'Rear wheel'],
          ] as const
        ).map(([k, label]) => (
          <label key={k} className={`chip ${wheel === k ? 'chip-on' : ''}`}>
            <input type="radio" className="sr-only" name="swap-tube-wheel" checked={wheel === k} onChange={() => setWheel(k)} />
            {label}
          </label>
        ))}
      </div>
      {opts.loading && !opts.data ? (
        <Loading />
      ) : opts.error ? (
        <ErrorBox error={opts.error} onRetry={opts.reload} />
      ) : opts.data?.installed_component_id ? (
        <ReplaceForm key={opts.data.installed_component_id} componentId={opts.data.installed_component_id} onDone={(c) => onDone(c.notice)} />
      ) : (
        opts.data && (
          <>
            <fieldset className="field">
              <legend className="field-label">New tube</legend>
              <SourcePick name="swap-tube-src" options={{ ...opts.data, replace: true }} isPart={false} value={source} onChange={setSource} />
            </fieldset>
            {opts.data.stock.length === 0 && <p className="small muted">No tubes in stock. Add them under Inventory → Stock so the count drops when you use one.</p>}
            <Field label="Swapped on">
              <input type="date" value={at} onChange={(e) => setAt(e.target.value)} />
            </Field>
            <FormError error={err} />
            <div className="form-actions">
              <button className="btn btn-primary" disabled={busy || !source} onClick={save}>
                Swap tube
              </button>
            </div>
          </>
        )
      )}
    </div>
  )
}
