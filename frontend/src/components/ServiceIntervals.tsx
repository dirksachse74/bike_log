// Settings → Service intervals: one place for every reminder's default (Dirk 2026-11-02: "a place where we can
// administer that. like how long hot wax lasts, how long liquid wax lasts, how long i can go without charging").
// Each value applies to all parts of that type; a part (or bike) with its own value keeps it.
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../context'
import { useApi } from '../hooks'
import type { Rule } from '../types'
import { Card, ErrorBox, Field, FormError, Loading, Sheet } from './ui'

type IntervalRule = Rule & { own_values?: number }

const CHARGING = ['BATTERY_CHARGE', 'POWER_CHARGE', 'COIN_CELL_REPLACE']
const FIRST = ['Chain and waxing', 'Charging and batteries', 'Brakes']

const n = (v: number | null | undefined) => (v == null ? '' : v.toLocaleString())

function describeRule(r: IntervalRule): string {
  if (r.trigger === 'CYCLE_WINDOW') return `once per hot-wax cycle, ${n(r.window_min_km)}–${n(r.window_max_km)} km after the hot wax`
  if (r.trigger === 'PARENT_COUNT') return `replace after it has been on ${r.interval_count} chains`
  if (r.trigger === 'ONCE_AFTER_INSTALL') return `once after fitting${r.window_max_km ? ` (within ${n(r.window_max_km)} km)` : ''}`
  const every = [r.interval_km && `${n(r.interval_km)} km`, r.interval_hours && `${n(r.interval_hours)} h of riding`, r.interval_months && `${r.interval_months} months`].filter(Boolean)
  let t = every.length ? `every ${every.join(' or ')}${every.length > 1 ? ', whichever comes first' : ''}` : 'no interval set'
  if (r.after_top_up_km) t += `; after a liquid wax top-up: ${n(r.after_top_up_km)} km later`
  const warn = [r.interval_km && r.warn_km && `${n(r.warn_km)} km`, r.interval_hours && r.warn_hours && `${n(r.warn_hours)} h`, r.interval_months && r.warn_days && `${r.warn_days} days`].filter(Boolean)
  if (warn.length) t += ` · reminds you ${warn.join(' / ')} before`
  return t
}

export default function ServiceIntervals() {
  const { meta, toast } = useApp()
  const rules = useApi<IntervalRule[]>('/rules')
  const [edit, setEdit] = useState<IntervalRule | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const { search } = useLocation()
  useEffect(() => {
    if (new URLSearchParams(search).get('section') === 'intervals' && rules.data) ref.current?.scrollIntoView({ block: 'start' })
  }, [search, rules.data])
  const typeOf = (c: string | null) => meta.component_types.find((t) => t.code === c)
  const group = (r: IntervalRule) =>
    r.component_type === 'CHAIN' ? 'Chain and waxing'
      : CHARGING.includes(r.action_code) ? 'Charging and batteries'
        : r.component_type === 'BIKE' ? 'Whole bike'
          : typeOf(r.component_type)?.category ?? 'Other'
  const groups = new Map<string, IntervalRule[]>()
  for (const r of rules.data ?? []) groups.set(group(r), [...(groups.get(group(r)) ?? []), r])
  const order = [...groups.keys()].sort((a, b) => {
    const rank = (g: string) => (FIRST.includes(g) ? FIRST.indexOf(g) : g === 'Whole bike' ? 99 : 10)
    return rank(a) - rank(b) || a.localeCompare(b)
  })
  return (
    <div ref={ref} id="intervals" className="span-2">
      <Card title="Service intervals" className="span-2">
        <p className="small">
          How long things last before a reminder comes up: waxing, charging, brake fluid and every other check. A value here applies to all parts of that type. A part with its own value (set on the part's page under Rules) keeps it.
        </p>
        {rules.loading && !rules.data && <Loading />}
        {rules.error && <ErrorBox error={rules.error} onRetry={rules.reload} />}
        {order.map((g) => (
          <details key={g} className="interval-group">
            <summary>
              {g} <span className="muted small">({groups.get(g)!.length})</span>
            </summary>
            <ul className="list">
              {groups.get(g)!.map((r) => (
                <li key={r.id} data-rule={r.rule_code}>
                  <span>
                    <strong>{r.name}</strong>
                    <span className="muted small"> · {r.component_type === 'BIKE' ? 'whole bike' : typeOf(r.component_type)?.name.toLowerCase() ?? r.component_type}</span>
                    <br />
                    <span className="small">
                      {r.active ? describeRule(r) : 'switched off'}
                      {r.own_values ? ` · ${r.own_values} part${r.own_values === 1 ? '' : 's'} or bike${r.own_values === 1 ? '' : 's'} with their own value` : ''}
                    </span>
                    {r.notes && <span className="small muted interval-note"><br />{r.notes}</span>}
                  </span>
                  <button className="btn btn-small" onClick={() => setEdit(r)} aria-label={`Edit ${r.name} (${r.component_type})`}>
                    Edit
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </Card>
      {edit && (
        <Sheet title={`${edit.name}: default for every ${edit.component_type === 'BIKE' ? 'bike' : typeOf(edit.component_type)?.name.toLowerCase()}`} onClose={() => setEdit(null)}>
          <IntervalForm
            rule={edit}
            onDone={() => {
              toast(`${edit.name}: saved.`)
              setEdit(null)
              rules.reload()
            }}
          />
        </Sheet>
      )}
    </div>
  )
}

function IntervalForm({ rule, onDone }: { rule: IntervalRule; onDone: () => void }) {
  const s = (v: number | null | undefined) => (v == null ? '' : String(v))
  const [f, setF] = useState({
    interval_km: s(rule.interval_km), interval_hours: s(rule.interval_hours), interval_months: s(rule.interval_months),
    warn_km: s(rule.warn_km), warn_hours: s(rule.warn_hours), warn_days: s(rule.warn_days),
    window_min_km: s(rule.window_min_km), window_max_km: s(rule.window_max_km), interval_count: s(rule.interval_count),
    after_top_up_km: s(rule.after_top_up_km), active: rule.active,
  })
  const [err, setErr] = useState<string | null>(null)
  const num = (v: string) => (v.trim() === '' ? null : Number(v.replace(',', '.')))
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  async function save() {
    setErr(null)
    const body: Record<string, unknown> = { active: f.active }
    if (rule.trigger === 'INTERVAL')
      Object.assign(body, {
        interval_km: num(f.interval_km), interval_hours: num(f.interval_hours), interval_months: num(f.interval_months),
        warn_km: num(f.warn_km), warn_hours: num(f.warn_hours), warn_days: num(f.warn_days),
        ...(rule.action_code === 'WAX_HOT' ? { after_top_up_km: num(f.after_top_up_km) } : {}),
      })
    else if (rule.trigger === 'PARENT_COUNT') Object.assign(body, { interval_count: num(f.interval_count) })
    else Object.assign(body, { window_min_km: num(f.window_min_km), window_max_km: num(f.window_max_km), warn_km: num(f.warn_km) })
    try {
      await api.patch(`/rules/${rule.id}`, body)
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="form">
      {rule.notes && <p className="small muted">{rule.notes}</p>}
      {rule.trigger === 'INTERVAL' && (
        <>
          <div className="row">
            <Field label="Every … km"><input inputMode="decimal" value={f.interval_km} onChange={set('interval_km')} /></Field>
            <Field label="or every … hours of riding"><input inputMode="decimal" aria-label="Every … hours of riding" value={f.interval_hours} onChange={set('interval_hours')} /></Field>
            <Field label="or every … months"><input inputMode="numeric" value={f.interval_months} onChange={set('interval_months')} /></Field>
          </div>
          {rule.action_code === 'WAX_HOT' && (
            <Field label="After a liquid wax top-up: hot wax … km later" hint="e.g. 200: a top-up at 70 km moves the hot wax to 270 km. Empty: top-ups do not move it.">
              <input inputMode="decimal" aria-label="Hot wax km after a top-up" value={f.after_top_up_km} onChange={set('after_top_up_km')} />
            </Field>
          )}
          <div className="row">
            <Field label="Remind … km before"><input inputMode="decimal" value={f.warn_km} onChange={set('warn_km')} /></Field>
            <Field label="… hours before"><input inputMode="decimal" aria-label="Remind … hours before" value={f.warn_hours} onChange={set('warn_hours')} /></Field>
            <Field label="… days before"><input inputMode="numeric" aria-label="Remind … days before" value={f.warn_days} onChange={set('warn_days')} /></Field>
          </div>
        </>
      )}
      {rule.trigger === 'PARENT_COUNT' && (
        <Field label="Replace after it has been on … parts"><input inputMode="numeric" value={f.interval_count} onChange={set('interval_count')} /></Field>
      )}
      {(rule.trigger === 'CYCLE_WINDOW' || rule.trigger === 'ONCE_AFTER_INSTALL') && (
        <div className="row">
          {rule.trigger === 'CYCLE_WINDOW' && <Field label="From … km after the hot wax"><input inputMode="decimal" value={f.window_min_km} onChange={set('window_min_km')} /></Field>}
          <Field label={rule.trigger === 'CYCLE_WINDOW' ? 'to … km after the hot wax' : 'Within … km after fitting'}><input inputMode="decimal" value={f.window_max_km} onChange={set('window_max_km')} /></Field>
        </div>
      )}
      <label className="check">
        <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Reminder on
      </label>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" onClick={save}>Save for all {rule.component_type === 'BIKE' ? 'bikes' : 'parts of this type'}</button>
      </div>
    </div>
  )
}
