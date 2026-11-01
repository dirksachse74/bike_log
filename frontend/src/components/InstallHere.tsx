// One short way to put a part on (DECISIONS 107): pick where (front or rear wheel, a position on the bike),
// then a spare from storage or a new part, a date, Save. Used for "Install a tire" on the wheel, wheelset and
// bike pages, and for "Install" on the page of a stored part (then the part is fixed and only "where" is asked).
import { useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { toCents, today, usageText } from '../format'
import { useApi } from '../hooks'
import type { ComponentSummary } from '../types'
import type { MountTarget, MountTargets } from './MountPicker'
import ShopPicker from './ShopPicker'
import { Field, FormError, Loading } from './ui'

const pretty = (t: MountTarget) => {
  if (t.parent_type === 'FRONT_WHEEL') return `Front wheel · ${t.parent_label}`
  if (t.parent_type === 'REAR_WHEEL') return `Rear wheel · ${t.parent_label}`
  return t.text
}

export default function InstallHere({ componentType, bikeId, under, part, onDone, onCancel, onChange }: {
  componentType: string
  bikeId?: number // only positions of this bike
  under?: number // only positions on this part or parts mounted on it (a wheel, a wheelset)
  part?: ComponentSummary // install this stored part (no "spare or new" question)
  onDone: (msg: string) => void
  onCancel: () => void
  onChange?: (occupiedId: number) => void // a taken position: change the part that is there instead
}) {
  const { meta } = useApp()
  const ctype = meta.component_types.find((t) => t.code === componentType)
  const noun = ctype?.name.toLowerCase() ?? 'part'
  const q = useApi<MountTargets>(`/mount-targets?component_type=${componentType}${bikeId ? `&bike_id=${bikeId}` : ''}${under ? `&under=${under}` : ''}`)
  const spares = useApi<ComponentSummary[]>(part ? null : `/components?state=STORED&component_type=${componentType}`)
  const targets = q.data?.targets ?? []
  const free = targets.filter((t) => !t.occupied_by)
  const [pick, setPick] = useState<number | null>(null)
  const chosen = pick ?? (free.length === 1 ? targets.indexOf(free[0]) : null)
  const spareList = (spares.data ?? []).filter((c) => c.status === 'ACTIVE')
  const [src, setSrc] = useState<'spare' | 'new' | null>(null)
  const source = part ? 'spare' : src ?? (spareList.length ? 'spare' : 'new')
  const [f, setF] = useState({ spare: '', label: '', price: '', purchase_date: '', shop: '', at: today() })
  const [err, setErr] = useState<string | null>(null)
  const [opId] = useState(newOpId)
  const groups = [...new Set(targets.map((t) => t.group))]

  async function save() {
    setErr(null)
    if (chosen === null) return setErr(`Pick where the ${noun} goes.`)
    const t = targets[chosen]
    const where: Record<string, unknown> = { at: f.at, slot: t.slot ?? undefined }
    if (t.parent_component_id) where.parent_component_id = t.parent_component_id
    else where.bike_id = t.bike_id
    try {
      if (source === 'spare') {
        const id = part?.id ?? Number(f.spare)
        if (!id) return setErr(`Pick the ${noun} from storage.`)
        await api.post(`/components/${id}/install`, where, opId)
        onDone(`${part?.label ?? spareList.find((c) => c.id === id)?.label} installed: ${pretty(t)}.`)
      } else {
        if (!f.label.trim()) return setErr(`Give the new ${noun} a name, e.g. "GP5000 front".`)
        const price = toCents(f.price)
        if (Number.isNaN(price)) return setErr('Price: enter an amount such as 49,90')
        const body: Record<string, unknown> = { component_type: componentType, label: f.label.trim(), prior_usage: 'NEW', install: where }
        if (price !== null) body.price_cents = price
        if (f.purchase_date) body.purchase_date = f.purchase_date
        if (f.shop.trim()) body.shop = f.shop.trim()
        const c = await api.post<ComponentSummary>('/components', body, opId)
        onDone(`${c.label} installed: ${pretty(t)}.`)
      }
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  if (q.loading && !q.data) return <Loading />
  return (
    <div className="form install-here">
      <div className="field">
        <span className="field-label">Where does it go?</span>
        <div role="radiogroup" aria-label="Where does it go?" className="where-list">
          {targets.length === 0 && <span className="small muted">Nowhere to put a {noun} yet{ctype?.parent_types.length ? `: it goes on a ${ctype.parent_types.map((p) => meta.component_types.find((x) => x.code === p)?.name.toLowerCase() ?? p).join(' or ')}` : ''}.</span>}
          {groups.map((g) => (
            <div key={g}>
              {groups.length > 1 && <div className="small muted">{g}</div>}
              {targets.map((t, i) =>
                t.group !== g ? null : (
                  <label key={i} className={`check ${t.occupied_by ? 'muted' : ''}`}>
                    <input type="radio" name="where" disabled={!!t.occupied_by} checked={chosen === i} onChange={() => setPick(i)} /> {pretty(t)}
                    {t.occupied_by && (
                      <>
                        {' '}
                        <span className="small">has {t.occupied_by}</span>
                        {onChange && t.occupied_id && (
                          <>
                            {' '}
                            <button type="button" className="btn btn-small" onClick={() => onChange(t.occupied_id!)}>
                              Change it
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </label>
                ),
              )}
            </div>
          ))}
        </div>
      </div>
      {!part && (
        <>
          <div className="chips" role="radiogroup" aria-label={`Which ${noun}`}>
            <button type="button" className={`chip ${source === 'spare' ? 'chip-on' : ''}`} disabled={!spareList.length} onClick={() => setSrc('spare')}>
              A spare from storage{spareList.length ? ` (${spareList.length})` : ' (none)'}
            </button>
            <button type="button" className={`chip ${source === 'new' ? 'chip-on' : ''}`} onClick={() => setSrc('new')}>
              A new {noun}
            </button>
          </div>
          {source === 'spare' ? (
            <Field label={`${ctype?.name ?? 'Part'} from storage`}>
              <select value={f.spare} onChange={(e) => setF({ ...f, spare: e.target.value })}>
                <option value="">Pick…</option>
                {spareList.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} ({usageText(c.usage)})
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <>
              <Field label="Name / label" hint="e.g. GP5000 front. It is new, so it starts at 0 km.">
                <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
              </Field>
              <div className="row">
                <Field label="Price paid (optional)">
                  <input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="€" />
                </Field>
                <Field label="Bought on (optional)">
                  <input type="date" value={f.purchase_date} onChange={(e) => setF({ ...f, purchase_date: e.target.value })} />
                </Field>
              </div>
              <div className="row">
                <ShopPicker value={f.shop} onChange={(v) => setF({ ...f, shop: v })} />
              </div>
            </>
          )}
        </>
      )}
      <Field label="Installed on" hint="Rides from this day on count on it.">
        <input type="date" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
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
