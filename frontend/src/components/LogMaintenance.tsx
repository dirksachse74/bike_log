import { useEffect, useMemo, useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { toCents, today } from '../format'
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
const onBike = (a: ActionDef) => a.targets.includes('BIKE')

/** The outcome a measurement implies, as the server will set it when no outcome is picked. */
function implied(a: ActionDef, raw: string, unit: string): string | null {
  const v = Number(raw.replace(',', '.'))
  if (!a.limits?.length || !raw || Number.isNaN(v)) return null
  if (unit && a.unit && unit.trim().toLowerCase() !== a.unit.toLowerCase()) return null
  const hit = a.limits.find((l) => (l.below ? v <= l.value : v >= l.value))
  return hit ? hit.outcome : 'OK'
}

/** "Done: a; b. Not done: c. <own text>" so the entry records which checklist jobs were ticked. */
function checklistText(items: string[], ticked: string[], own: string): string {
  const done = items.filter((i) => ticked.includes(i))
  const open = items.filter((i) => !ticked.includes(i))
  return [done.length ? `Done: ${done.join('; ')}.` : '', open.length ? `Not done: ${open.join('; ')}.` : '', own.trim()].filter(Boolean).join(' ')
}

/** Short, contextual maintenance entry: bike → action → installed parts preselected → date → save. */
export default function LogMaintenance({ bikeId, componentId, actionCode, onDone }: Props) {
  const { meta } = useApp()
  const bikes = useApi<Bike[]>('/bikes')
  const comp = useApi<{ id: number; label: string; component_type: string; location: { bike_id?: number | null } }>(componentId ? `/components/${componentId}` : null)
  const [bike, setBike] = useState<number | null>(bikeId ?? null)
  const detail = useApi<BikeDetail>(bike && !componentId ? `/bikes/${bike}` : null)
  const [action, setAction] = useState<string | null>(actionCode ?? null)
  const [selected, setSelected] = useState<number[]>(componentId ? [componentId] : [])
  const [form, setForm] = useState({ at: today(), symptom: '', work_done: '', outcome: '', measurement_value: '', measurement_unit: '', consumable_id: '', consumable_qty: '', notes: '', cost: '' })
  const [ticked, setTicked] = useState<string[]>([])
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
      .concat(meta.actions.filter(onBike))
      .concat(meta.actions.filter((a) => a.targets.includes('*')))
  }, [meta.actions, setup, componentId, comp.data])
  const act = meta.actions.find((a) => a.code === action) ?? null
  const bikeLevel = !!act && !componentId && onBike(act)
  const candidates = act && !componentId && !bikeLevel ? setup.filter((s) => applies(act, s.component_type)) : []

  useEffect(() => {
    // preselect every installed part the action applies to (e.g. both tires for "top up sealant")
    setTicked([])
    if (act && !componentId) setSelected(setup.filter((s) => applies(act, s.component_type) && !act.targets.includes('*')).map((s) => s.component_id))
  }, [action]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  async function save() {
    if (!act) return setError('Pick what you did.')
    if (!bikeLevel && !selected.length) return setError('Pick at least one part.')
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { action_code: act.code, at: form.at }
      for (const k of ['symptom', 'work_done', 'outcome', 'measurement_unit', 'notes'] as const) if (form[k]) body[k] = form[k]
      if (act.checklist?.length) body.work_done = checklistText(act.checklist, ticked, form.work_done)
      if (form.measurement_value) body.measurement_value = Number(form.measurement_value.replace(',', '.'))
      if (form.consumable_id) body.consumable_id = Number(form.consumable_id)
      if (form.consumable_qty) body.consumable_qty = Number(form.consumable_qty.replace(',', '.'))
      const cost = toCents(form.cost)
      if (Number.isNaN(cost)) throw new Error('Cost: enter an amount such as 25,00')
      if (cost !== null) body.cost_cents = cost
      if (bikeLevel) {
        body.bike_id = bike
        await api.post('/maintenance/events', body, opId)
        return onDone(`${act.name} logged for ${bikes.data?.find((b) => b.id === bike)?.name ?? 'the bike'}.`)
      }
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
      {bikeLevel && <p className="muted small">Logged for the whole bike.</p>}
      {act && !componentId && !bikeLevel && (
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
          {!!act.checklist?.length && (
            <Field label="Checklist" hint="Tick what you did; it is saved with the entry. Each job keeps its own reminder on its part.">
              <ul className="checklist">
                {act.checklist.map((item) => (
                  <li key={item}>
                    <label>
                      <input type="checkbox" checked={ticked.includes(item)} onChange={(e) => setTicked(e.target.checked ? [...ticked, item] : ticked.filter((x) => x !== item))} />
                      {item}
                    </label>
                  </li>
                ))}
              </ul>
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
              <Field
                label="Measurement"
                hint={
                  implied(act, form.measurement_value, form.measurement_unit) && !form.outcome
                    ? `Outcome will be: ${implied(act, form.measurement_value, form.measurement_unit)!.replace(/_/g, ' ').toLowerCase()}`
                    : act.limits_source ?? undefined
                }
              >
                <input inputMode="decimal" aria-label="Measurement" value={form.measurement_value} onChange={set('measurement_value')} placeholder="0.3" />
              </Field>
              <Field label="Unit">
                <input value={form.measurement_unit} onChange={set('measurement_unit')} placeholder={act.unit ?? '% / mm'} />
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
          <div className="row">
            <Field label="Notes (optional)">
              <input value={form.notes} onChange={set('notes')} />
            </Field>
            <Field label="Cost (optional)" hint="Shop fee or service price; supplies from stock are counted separately.">
              <input inputMode="decimal" value={form.cost} onChange={set('cost')} placeholder="€" />
            </Field>
          </div>
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
