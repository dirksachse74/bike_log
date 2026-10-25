import { useEffect, useMemo, useState } from 'react'
import { api, newOpId } from '../api'
import { useApi } from '../hooks'
import { euro, toCents, today } from '../format'
import type { Bike, GroupsetPlan, GroupsetTemplate, OpResult } from '../types'
import { Empty, ErrorBox, Field, FormError, Loading, Tag } from './ui'

const ACTION_TEXT: Record<string, string> = { INSTALL: 'install', REPLACE: 'replace', SPARE: 'spare' }

// Adds every part of a groupset in one step. All logic (positions, occupied slots, products) is in
// the backend; this form only collects the choices and shows the plan before anything is saved.
export default function GroupsetImport({ bikeId, onDone }: { bikeId?: number; onDone: (msg: string) => void }) {
  const templates = useApi<GroupsetTemplate[]>('/groupsets')
  const bikes = useApi<Bike[]>('/bikes')
  const [code, setCode] = useState('')
  const [bike, setBike] = useState(bikeId ? String(bikeId) : '')
  const [options, setOptions] = useState<Record<string, string>>({})
  const [include, setInclude] = useState<Set<string>>(new Set())
  const [occupied, setOccupied] = useState('KEEP')
  const [at, setAt] = useState(today())
  const [priorUsage, setPriorUsage] = useState('NEW')
  const [prices, setPrices] = useState<Record<string, string>>({})
  // How it was bought: one price for the whole set (a bundle) or a price per part.
  const [priceMode, setPriceMode] = useState<'BUNDLE' | 'PARTS'>('BUNDLE')
  const [bundle, setBundle] = useState({ price: '', merchant: '', purchased_on: today() })
  const [spares, setSpares] = useState<Set<string>>(new Set())
  const [plan, setPlan] = useState<GroupsetPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const t = templates.data?.find((x) => x.code === code)

  useEffect(() => {
    if (!code && templates.data?.length) setCode(templates.data[0].code)
  }, [code, templates.data])
  useEffect(() => {
    if (!t) return
    setOptions(Object.fromEntries(t.options.map((o) => [o.key, o.default])))
    setInclude(new Set(t.items.filter((i) => i.default).map((i) => i.key)))
  }, [t])

  const offered = useMemo(
    () => (t ? t.items.filter((i) => !i.when || Object.entries(i.when).every(([k, v]) => v.includes(options[k]))) : []),
    [t, options],
  )
  const body = () => ({
    bike_id: bike ? Number(bike) : null,
    options,
    include: offered.filter((i) => include.has(i.key)).map((i) => i.key),
    occupied,
    to_spares: [...spares].filter((k) => include.has(k)),
  })

  // The preview follows every change, so what you see is what "Add" will do.
  useEffect(() => {
    if (!t || Object.keys(options).length === 0) return
    let live = true
    api
      .post<GroupsetPlan>(`/groupsets/${t.code}/plan`, body())
      .then((p) => live && (setPlan(p), setError(null)))
      .catch((e: Error) => live && (setPlan(null), setError(e.message)))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, bike, options, include, occupied, offered, spares])

  async function add() {
    if (!t) return
    setBusy(true)
    setError(null)
    try {
      const paid: Record<string, number> = {}
      let bundleBody = null
      if (priceMode === 'PARTS') {
        for (const key of body().include) {
          const c = toCents(prices[key] ?? '')
          if (Number.isNaN(c)) throw new Error('Prices: enter amounts such as 49,90')
          if (c !== null) paid[key] = c
        }
      } else {
        const c = toCents(bundle.price)
        if (Number.isNaN(c)) throw new Error('Bundle price: enter an amount such as 1899,00')
        bundleBody = { price_cents: c, merchant: bundle.merchant || null, purchased_on: bundle.purchased_on || null }
      }
      const r = await api.post<OpResult<GroupsetPlan & { created: { label: string }[]; bundle: { name: string } | null }>>(
        `/groupsets/${t.code}/import`,
        { ...body(), at, prior_usage: priorUsage, prices: paid, bundle: bundleBody, purchase_date: priceMode === 'BUNDLE' ? bundle.purchased_on || null : null },
        opId,
      )
      onDone(
        `${r.result.created.length} parts added (${r.result.counts.INSTALL + r.result.counts.REPLACE} installed)${r.result.bundle ? `, recorded as the bundle "${r.result.bundle.name}"` : ''}. Undo is under Inventory → History.`,
      )
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (templates.loading && !templates.data) return <Loading />
  if (templates.error) return <ErrorBox error={templates.error} onRetry={templates.reload} />
  if (!t) return <Empty title="No groupset templates" />
  const paidTotal = offered.filter((i) => include.has(i.key)).reduce((sum, i) => sum + (toCents(prices[i.key] ?? '') || 0), 0)
  const toggleSpare = (key: string) => {
    const next = new Set(spares)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setSpares(next)
  }
  const toggle = (key: string) => {
    const next = new Set(include)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setInclude(next)
  }
  return (
    <div className="form">
      {(templates.data?.length ?? 0) > 1 && (
        <Field label="Groupset">
          <select value={code} onChange={(e) => setCode(e.target.value)}>
            {templates.data?.map((x) => (
              <option key={x.code} value={x.code}>
                {x.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      <p className="small">
        <strong>{t.name}</strong> {!t.verified && <Tag tone="warn" title={t.source}>specs not verified with Shimano yet</Tag>}
        <br />
        <span className="muted">{t.notes}</span>
      </p>
      <div className="row">
        <Field label="Bike">
          <select value={bike} onChange={(e) => setBike(e.target.value)}>
            <option value="">No bike: add everything as spares</option>
            {bikes.data
              ?.filter((b) => b.status === 'ACTIVE')
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Installed on" hint="Rides from this date count on the new parts.">
          <input type="date" value={at} onChange={(e) => setAt(e.target.value)} />
        </Field>
      </div>
      <div className="row options">
        {t.options.map((o) => (
          <Field key={o.key} label={o.label}>
            <select value={options[o.key] ?? o.default} onChange={(e) => setOptions({ ...options, [o.key]: e.target.value })}>
              {o.choices.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </Field>
        ))}
        <Field label="Condition">
          <select value={priorUsage} onChange={(e) => setPriorUsage(e.target.value)}>
            <option value="NEW">New</option>
            <option value="UNKNOWN">Used, mileage unknown</option>
          </select>
        </Field>
      </div>
      {bike && (
        <fieldset className="field">
          <legend className="field-label">If a position already has a part</legend>
          <div className="pick-list">
            {t.occupied_modes.map((m) => (
              <label key={m.code} className={`pick ${occupied === m.code ? 'pick-on' : ''}`}>
                <input type="radio" name="occupied" checked={occupied === m.code} onChange={() => setOccupied(m.code)} />
                <span>
                  {m.label}
                  {m.code === 'REPLACE' && <span className="small muted"> (old parts keep their history; worn ones are marked discarded, others go to spares)</span>}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <fieldset className="field">
        <legend className="field-label">How was it bought?</legend>
        <div className="pick-list">
          <label className={`pick ${priceMode === 'BUNDLE' ? 'pick-on' : ''}`}>
            <input type="radio" name="priceMode" checked={priceMode === 'BUNDLE'} onChange={() => setPriceMode('BUNDLE')} />
            <span>
              As one bundle (one price for the whole set)
              <span className="small muted"> The price counts once. Parts replaced later get their own price; the originals stay in the bundle.</span>
            </span>
          </label>
          <label className={`pick ${priceMode === 'PARTS' ? 'pick-on' : ''}`}>
            <input type="radio" name="priceMode" checked={priceMode === 'PARTS'} onChange={() => setPriceMode('PARTS')} />
            <span>Part by part (a price per part)</span>
          </label>
        </div>
        {priceMode === 'BUNDLE' && (
          <div className="row">
            <Field label="Bundle price" hint="Optional; can be added later.">
              <input inputMode="decimal" placeholder="€" value={bundle.price} onChange={(e) => setBundle({ ...bundle, price: e.target.value })} />
            </Field>
            <Field label="Shop">
              <input value={bundle.merchant} onChange={(e) => setBundle({ ...bundle, merchant: e.target.value })} />
            </Field>
            <Field label="Bought on">
              <input type="date" value={bundle.purchased_on} onChange={(e) => setBundle({ ...bundle, purchased_on: e.target.value })} />
            </Field>
          </div>
        )}
      </fieldset>
      <fieldset className="field">
        <legend className="field-label">
          Parts ({offered.filter((i) => include.has(i.key)).length} of {offered.length})
          {priceMode === 'PARTS' ? ` · prices are optional${paidTotal > 0 ? `, ${euro(paidTotal)} entered` : ''}` : ''}
          {bike ? ' · tick "spare" for parts that go into storage instead of onto the bike' : ''}
        </legend>
        <ul className="list groupset-items">
          {offered.map((i) => {
            const row = plan?.items.find((r) => r.key === i.key)
            return (
              <li key={i.key}>
                <label className="check">
                  <input type="checkbox" checked={include.has(i.key)} onChange={() => toggle(i.key)} />
                  <span>
                    <strong>{row?.label ?? i.name}</strong>
                    <span className="small muted"> {row ? `${row.model} · ${row.text}` : i.type_name}</span>
                  </span>
                </label>
                {row && <Tag tone={row.action === 'SPARE' ? 'neutral' : row.action === 'REPLACE' ? 'warn' : 'good'}>{ACTION_TEXT[row.action]}</Tag>}
                {bike && include.has(i.key) && (
                  <label className="check small" title="Keep this part in storage instead of installing it">
                    <input type="checkbox" aria-label={`Keep ${i.name} as spare`} checked={spares.has(i.key)} onChange={() => toggleSpare(i.key)} /> spare
                  </label>
                )}
                {priceMode === 'PARTS' && include.has(i.key) && (
                  <input
                    className="price-input"
                    aria-label={`Price ${i.name}`}
                    inputMode="decimal"
                    value={prices[i.key] ?? ''}
                    placeholder={row?.list_price_cents ? euro(row.list_price_cents) : '€'}
                    onChange={(e) => setPrices({ ...prices, [i.key]: e.target.value })}
                  />
                )}
              </li>
            )
          })}
        </ul>
      </fieldset>
      {plan && (
        <div className="notice notice-preview">
          {plan.counts.INSTALL} to install, {plan.counts.REPLACE} to replace, {plan.counts.SPARE} as spares
          {plan.new_products ? `; ${plan.new_products} new product${plan.new_products === 1 ? '' : 's'} with Shimano specs` : ''}. Nothing is saved
          until you press Add.
        </div>
      )}
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={!plan || busy} onClick={add}>
          {busy ? 'Adding…' : `Add ${plan?.items.length ?? ''} parts`}
        </button>
      </div>
    </div>
  )
}
