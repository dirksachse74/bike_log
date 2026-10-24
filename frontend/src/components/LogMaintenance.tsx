import { useEffect, useMemo, useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { today } from '../format'
import { useApi } from '../hooks'
import type { ActionDef, Bike, SetupRow } from '../types'
import { Field, FormError, Loading } from './ui'

interface Props {
  bikeId?: number | null
  componentId?: number | null
  actionCode?: string | null
  onDone: (msg: string) => void
}

interface BikeDetail extends Bike {
  setup: SetupRow[]
}

const applies = (a: ActionDef, type: string) => a.targets.includes('*') || a.targets.includes(type)

/** Short, contextual maintenance entry: bike → action → installed parts preselected → date → save. */
export default function LogMaintenance({ bikeId, componentId, actionCode, onDone }: Props) {
  const { meta } = useApp()
  const bikes = useApi<Bike[]>('/bikes')
  const comp = useApi<{ id: number; label: string; component_type: string; location: { bike_id?: number | null } }>(componentId ? `/components/${componentId}` : null)
  const [bike, setBike] = useState<number | null>(bikeId ?? null)
  const detail = useApi<BikeDetail>(bike && !componentId ? `/bikes/${bike}` : null)
  const [action, setAction] = useState<string | null>(actionCode ?? null)
  const [selected, setSelected] = useState<number[]>(componentId ? [componentId] : [])
  const [form, setForm] = useState({ at: today(), symptom: '', work_done: '', outcome: '', measurement_value: '', measurement_unit: '', consumable_id: '', consumable_qty: '', notes: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const consumables = useApi<{ id: number; name: string; kind: string; unit: string }[]>('/consumables')

  useEffect(() => {
    if (!bike && !componentId && bikes.data?.length) setBike(bikes.data.find((b) => b.status === 'ACTIVE')?.id ?? bikes.data[0].id)
  }, [bikes.data, bike, componentId])

  const setup = useMemo(() => detail.data?.setup ?? [], [detail.data])
  const actions = useMemo(() => {
    if (componentId && comp.data) return meta.actions.filter((a) => applies(a, comp.data!.component_type))
    const types = new Set(setup.map((s) => s.component_type))
    return meta.actions.filter((a) => [...types].some((t) => applies(a, t)) && !a.targets.includes('*'))
      .concat(meta.actions.filter((a) => a.targets.includes('*')))
  }, [meta.actions, setup, componentId, comp.data])
  const act = meta.actions.find((a) => a.code === action) ?? null
  const candidates = act && !componentId ? setup.filter((s) => applies(act, s.component_type)) : []

  useEffect(() => {
    // preselect every installed part the action applies to (e.g. both tires for "top up sealant")
    if (act && !componentId) setSelected(setup.filter((s) => applies(act, s.component_type) && !act.targets.includes('*')).map((s) => s.component_id))
  }, [action]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  async function save() {
    if (!act) return setError('Pick what you did.')
    if (!selected.length) return setError('Pick at least one part.')
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { action_code: act.code, at: form.at }
      for (const k of ['symptom', 'work_done', 'outcome', 'measurement_unit', 'notes'] as const) if (form[k]) body[k] = form[k]
      if (form.measurement_value) body.measurement_value = Number(form.measurement_value.replace(',', '.'))
      if (form.consumable_id) body.consumable_id = Number(form.consumable_id)
      if (form.consumable_qty) body.consumable_qty = Number(form.consumable_qty.replace(',', '.'))
      if (selected.length === 1) body.component_id = selected[0]
      else body.component_ids = selected
      await api.post('/maintenance/events', body, opId)
      onDone(`${act.name} logged for ${selected.length} part${selected.length > 1 ? 's' : ''}.`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (bikes.loading || (componentId && comp.loading)) return <Loading />
  if (!componentId && !bikes.data?.length) return <p>Add a bike first (Bikes → Add bike).</p>

  return (
    <div className="form">
      {componentId ? (
        <p className="muted">
          Part: <strong>{comp.data?.label}</strong>
        </p>
      ) : (
        <Field label="Bike">
          <select value={bike ?? ''} onChange={(e) => setBike(Number(e.target.value))}>
            {bikes.data!.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      <div className="field">
        <span className="field-label">What did you do?</span>
        {detail.loading && <Loading />}
        <div className="chips">
          {actions.filter((a) => a.quick || a.code === action || componentId).map((a) => (
            <button key={a.code} type="button" className={`chip ${a.code === action ? 'chip-on' : ''}`} onClick={() => setAction(a.code)}>
              {a.name}
            </button>
          ))}
        </div>
        {!componentId && (
          <select className="mt" value={action ?? ''} onChange={(e) => setAction(e.target.value || null)}>
            <option value="">More actions…</option>
            {actions.map((a) => (
              <option key={a.code} value={a.code}>
                {a.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {act && !componentId && (
        <div className="field">
          <span className="field-label">On which installed parts?</span>
          {candidates.length === 0 && <span className="muted">No installed part on this bike takes this action.</span>}
          {candidates.map((c) => (
            <label key={c.component_id} className="check">
              <input type="checkbox" checked={selected.includes(c.component_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, c.component_id] : selected.filter((x) => x !== c.component_id))} />
              {c.label} <span className="muted">({c.type_name})</span>
            </label>
          ))}
        </div>
      )}
      {act && (
        <>
          <Field label="Date" hint="A date is enough; no time is invented.">
            <input type="date" value={form.at} onChange={set('at')} required />
          </Field>
          {act.fields.includes('symptom') && (
            <Field label="Symptom">
              <input value={form.symptom} onChange={set('symptom')} placeholder="e.g. spongy lever" />
            </Field>
          )}
          {act.fields.includes('work_done') && (
            <Field label="Work done">
              <input value={form.work_done} onChange={set('work_done')} placeholder="e.g. lever bleed, 5 ml oil" />
            </Field>
          )}
          {act.fields.includes('outcome') && (
            <Field label="Outcome">
              {act.outcomes.length ? (
                <select value={form.outcome} onChange={set('outcome')}>
                  <option value="">—</option>
                  {act.outcomes.map((o) => (
                    <option key={o} value={o}>
                      {o.replace(/_/g, ' ').toLowerCase()}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={form.outcome} onChange={set('outcome')} />
              )}
            </Field>
          )}
          {act.fields.includes('measurement') && (
            <div className="row">
              <Field label="Measurement">
                <input inputMode="decimal" value={form.measurement_value} onChange={set('measurement_value')} placeholder="0.3" />
              </Field>
              <Field label="Unit">
                <input value={form.measurement_unit} onChange={set('measurement_unit')} placeholder="% / mm" />
              </Field>
            </div>
          )}
          {act.fields.includes('consumable') && (
            <div className="row">
              <Field label="Product used (optional)">
                <select value={form.consumable_id} onChange={set('consumable_id')}>
                  <option value="">—</option>
                  {consumables.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Amount">
                <input inputMode="decimal" value={form.consumable_qty} onChange={set('consumable_qty')} placeholder="unknown" />
              </Field>
            </div>
          )}
          <Field label="Notes (optional)">
            <input value={form.notes} onChange={set('notes')} />
          </Field>
        </>
      )}
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || !act} onClick={save}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}
