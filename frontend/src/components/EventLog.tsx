import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../context'
import { centsInput, euro, toCents, when } from '../format'
import type { EventRow } from '../types'
import ShopPicker from './ShopPicker'
import { Empty, Field, FormError, Sheet, Tag } from './ui'

// Maintenance log with Edit and Delete on every entry. Delete removes the entry from the log, the reminders
// and the costs (supplies it used come back into stock); it is kept under "Deleted entries" to restore.
export default function EventLog({ events, onChanged, show = 'part', limit }: { events: EventRow[]; onChanged: () => void; show?: 'part' | 'bike' | 'both' | 'none'; limit?: number }) {
  const { toast } = useApp()
  const [editing, setEditing] = useState<EventRow | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const live = events.filter((e) => !e.voided).slice(0, limit)
  const deleted = events.filter((e) => e.voided)
  async function del(e: EventRow) {
    if (!window.confirm(`Delete "${e.action}" on ${when(e.performed_at)}? It disappears from the log and the reminders; you can restore it under "Deleted entries".`)) return
    setErr(null)
    try {
      await api.del(`/maintenance/events/${e.id}`)
      toast('Entry deleted. Restore it under "Deleted entries" if that was a mistake.')
      onChanged()
    } catch (x) {
      setErr((x as Error).message)
    }
  }
  async function restore(e: EventRow) {
    setErr(null)
    try {
      await api.post(`/maintenance/events/${e.id}/restore`, {})
      toast('Entry restored.')
      onChanged()
    } catch (x) {
      setErr((x as Error).message)
    }
  }
  const where = (e: EventRow) => (
    <>
      {(show === 'part' || show === 'both') && e.component_id && <Link to={`/inventory/${e.component_id}`}>{e.component}</Link>}
      {(show === 'bike' || show === 'both') && !e.component_id && e.bike && <span className="muted">{e.bike} (whole bike)</span>}
    </>
  )
  return (
    <>
      <FormError error={err} form={false} />
      {live.length === 0 ? (
        <Empty title="Nothing logged yet" />
      ) : (
        <ul className="list event-log">
          {live.map((e) => (
            <li key={e.id} data-event={e.id}>
              <span>{when(e.performed_at)}</span>
              <strong>{e.action}</strong>
              {where(e)}
              <span className="small">{details(e)}</span>
              {e.outcome && <Tag>{e.outcome.replace(/_/g, ' ').toLowerCase()}</Tag>}
              <span className="row-actions">
                <button className="btn btn-small" onClick={() => setEditing(e)}>
                  Edit
                </button>
                <button className="btn btn-small" onClick={() => del(e)}>
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {deleted.length > 0 && (
        <details className="deleted-entries">
          <summary className="small muted">Deleted entries ({deleted.length})</summary>
          <ul className="list">
            {deleted.map((e) => {
              const undone = (e.void_reason ?? '').startsWith('undone')
              return (
                <li key={e.id} className="excluded">
                  <span>{when(e.performed_at)}</span>
                  <span>{e.action}</span>
                  {where(e)}
                  {undone ? (
                    <span className="small muted">taken back with Undo of its session</span>
                  ) : (
                    <button className="btn btn-small" onClick={() => restore(e)}>
                      Restore
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        </details>
      )}
      {editing && (
        <Sheet title={`Edit: ${editing.action}`} onClose={() => setEditing(null)}>
          <EditEvent ev={editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); toast('Entry saved.'); onChanged() }} />
        </Sheet>
      )}
    </>
  )
}

function details(e: EventRow): string {
  return [e.symptom && `symptom: ${e.symptom}`, e.work_done, e.measurement_value !== null && `${e.measurement_value}${e.measurement_unit ?? ''}`, e.consumable, e.cost_cents ? euro(e.cost_cents) : null, e.shop ? `at ${e.shop}` : null, e.notes]
    .filter(Boolean)
    .join(' · ')
}

function EditEvent({ ev, onSaved, onCancel }: { ev: EventRow; onSaved: () => void; onCancel: () => void }) {
  const { meta } = useApp()
  const act = meta.actions.find((a) => a.code === ev.action_code)
  const [f, setF] = useState({
    at: ev.performed_at.slice(0, 10),
    symptom: ev.symptom ?? '',
    work_done: ev.work_done ?? '',
    outcome: ev.outcome ?? '',
    measurement: ev.measurement_value === null ? '' : String(ev.measurement_value),
    cost: centsInput(ev.cost_cents),
    notes: ev.notes ?? '',
    shop: ev.shop ?? '',
  })
  const [err, setErr] = useState<string | null>(null)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }))
  async function save() {
    setErr(null)
    const cost = toCents(f.cost)
    if (Number.isNaN(cost)) return setErr('Cost: enter an amount such as 12,50')
    const value = f.measurement.trim() === '' ? null : Number(f.measurement.replace(',', '.'))
    if (value !== null && Number.isNaN(value)) return setErr('Measurement: enter a number')
    // a date alone keeps the time the entry had (the order against that day's rides stays the same)
    const at = f.at === ev.performed_at.slice(0, 10) ? ev.performed_at : f.at
    try {
      await api.patch(`/maintenance/events/${ev.id}`, { at, symptom: f.symptom, work_done: f.work_done, outcome: f.outcome, measurement_value: value, cost_cents: cost, shop: f.shop.trim() || null, notes: f.notes })
      onSaved()
    } catch (x) {
      setErr((x as Error).message)
    }
  }
  const has = (field: string) => !act || act.fields.includes(field)
  return (
    <div className="form">
      <p className="small muted">
        {ev.component ?? ev.bike}
        {ev.consumable ? ` · used: ${ev.consumable} (to change what was done or the supplies, delete the entry and record it again)` : ''}
      </p>
      <div className="row">
        <Field label="Date">
          <input type="date" value={f.at} onChange={set('at')} />
        </Field>
        <Field label="Cost (optional)">
          <input inputMode="decimal" value={f.cost} onChange={set('cost')} placeholder="€" />
        </Field>
      </div>
      {has('symptom') && (
        <Field label="Symptom">
          <input value={f.symptom} onChange={set('symptom')} />
        </Field>
      )}
      {has('work_done') && (
        <Field label="Work done">
          <input value={f.work_done} onChange={set('work_done')} />
        </Field>
      )}
      {(ev.outcome || has('outcome')) && (
        <Field label="Outcome">
          {act && act.outcomes.length ? (
            <select value={f.outcome} onChange={set('outcome')}>
              <option value="">—</option>
              {act.outcomes.map((o) => (
                <option key={o} value={o}>
                  {o.replace(/_/g, ' ').toLowerCase()}
                </option>
              ))}
            </select>
          ) : (
            <input value={f.outcome} onChange={set('outcome')} />
          )}
        </Field>
      )}
      {(ev.measurement_value !== null || act?.unit) && (
        <Field label={`Measurement${ev.measurement_unit || act?.unit ? ` (${ev.measurement_unit || act?.unit})` : ''}`}>
          <input inputMode="decimal" value={f.measurement} onChange={set('measurement')} />
        </Field>
      )}
      <ShopPicker value={f.shop} onChange={(v) => setF((x) => ({ ...x, shop: v }))} label="Done by a bike shop (optional)" />
      <Field label="Notes">
        <textarea rows={2} value={f.notes} onChange={set('notes')} />
      </Field>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={save}>
          Save
        </button>
        <button className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
