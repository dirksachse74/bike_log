// Chains that take turns on a bike (Chain A, Chain B ...): which one is on, which are waxed and ready, which
// wait for wax; a one-click swap to the next ready chain, "Wax chains" for all dirty ones at once, and the
// rotation history. The 500 km hot-wax rule of the chain on the bike drives the prompt (services/chains.py).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { km, today, when } from '../format'
import { useApi } from '../hooks'
import type { ChainRotationData, ChainRow } from '../types'
import { Card, ErrorBox, Field, FormError, Loading, Sheet, Tag } from './ui'

const STATE: Record<string, [string, 'good' | 'warn' | 'bad' | 'info' | 'neutral']> = {
  INSTALLED: ['on the bike', 'info'],
  READY_TO_INSTALL: ['waxed, ready', 'good'],
  NEEDS_HOT_WAX: ['dirty, waiting for wax', 'warn'],
  NEW_UNWAXED: ['new, wax before use', 'warn'],
  UNKNOWN: ['no hot wax recorded', 'neutral'],
  WORN: ['worn, do not use', 'bad'],
  AWAITING_SERVICE: ['awaiting repair', 'warn'],
  RETIRED: ['retired', 'neutral'],
}

export function ChainName({ c }: { c: Pick<ChainRow, 'component_id' | 'label' | 'mark'> }) {
  return (
    <>
      <Link to={`/inventory/${c.component_id}`}>{c.label}</Link>
      {c.mark && <span className="mark" title="How this chain is marked">{c.mark}</span>}
    </>
  )
}

// A swap or wax happens after that day's rides: now for today, the end of the day for an earlier date
// (a date alone means the start of the day, which would move that day's rides to the new chain).
const afterRides = (date: string) => (date === today() ? new Date().toISOString() : `${date}T23:59`)

async function swapChain(bikeId: number, to: number) {
  return api.post<{ result: { text: string } }>(`/bikes/${bikeId}/chains/swap`, { to_component_id: to, at: afterRides(today()) }, newOpId())
}

export default function ChainRotation({ bikeId, refresh, onChanged }: { bikeId: number; refresh: unknown; onChanged: () => void }) {
  const { toast } = useApp()
  const { data, error, loading, reload } = useApi<ChainRotationData>(`/bikes/${bikeId}/chains`)
  const [waxing, setWaxing] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh])
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data || data.chains.length < 2) return null
  const done = (text: string) => {
    toast(text)
    reload()
    onChanged()
  }
  async function swap(to: number) {
    setErr(null)
    try {
      done((await swapChain(bikeId, to)).result.text)
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  const p = data.prompt
  return (
    <Card title="Chain rotation" className="span-2" actions={<button className="btn btn-small" onClick={() => setWaxing(true)}>Wax chains</button>}>
      {p && (
        <div className={`rotation-prompt ${p.kind === 'WAX' ? 'warn' : ''}`}>
          <span>{p.text}</span>
          {p.to ? (
            <button className="btn btn-primary btn-small" onClick={() => swap(p.to!)}>
              {p.kind === 'INSTALL' ? `Put ${p.to_label} on` : `Swap to ${p.to_label}`}
            </button>
          ) : (
            <button className="btn btn-primary btn-small" onClick={() => setWaxing(true)}>
              Wax chains
            </button>
          )}
        </div>
      )}
      <FormError error={err} />
      <ul className="list rotation">
        {data.chains.map((c) => {
          const [word, tone] = STATE[c.state] ?? [c.state.toLowerCase(), 'neutral']
          const ws = c.wax_status
          return (
            <li key={c.component_id} data-chain={c.label}>
              <strong>
                <ChainName c={c} />
              </strong>
              <Tag tone={tone}>{word}</Tag>
              <span className="small">
                {c.km_since_hot_wax !== null ? `${km(c.km_since_hot_wax, 0)} since hot wax` : 'no hot wax yet'}
                {ws && ws.status !== 'OK' && <span className="muted"> ({ws.status.replace('_', ' ').toLowerCase()})</span>}
              </span>
              <span className="muted small">
                {km(c.lifetime_km, 0)} lifetime · {c.wax_cycles} wax cycle{c.wax_cycles === 1 ? '' : 's'}
                {c.last_wear ? ` · wear ${c.last_wear.value ?? '?'}${c.last_wear.unit ?? ''} on ${when(c.last_wear.date)}` : ' · wear not measured'}
              </span>
              {c.state === 'READY_TO_INSTALL' && c.component_id !== data.on && (
                <button className="btn btn-small" onClick={() => swap(c.component_id)}>
                  Put on
                </button>
              )}
            </li>
          )
        })}
      </ul>
      <details className="task-group" data-group="rotation-history">
        <summary>
          <strong>Rotation history</strong>
          <span className="muted small">{data.timeline.filter((t) => t.kind === 'ON').length} turns on the bike</span>
        </summary>
        <ul className="list">
          {data.timeline.map((t, i) => (
            <li key={i}>
              <span>{when(t.date)}</span>
              {t.kind === 'ON' ? (
                <span>
                  <Link to={`/inventory/${t.component_id}`}>{t.label}</Link> on{t.until ? ` until ${when(t.until)}` : ', still on'} · {km(t.km ?? 0, 0)}
                </span>
              ) : (
                <span>
                  <Link to={`/inventory/${t.component_id}`}>{t.label}</Link> hot waxed
                </span>
              )}
            </li>
          ))}
        </ul>
      </details>
      <p className="small muted">A chain joins this rotation when it first goes on this bike, or on its page (Chain rotation). Give each chain a mark under Edit details so you can tell them apart.</p>
      {waxing && (
        <Sheet title="Wax chains" onClose={() => setWaxing(false)}>
          <WaxForm data={data} onDone={(t) => (setWaxing(false), done(t))} />
        </Sheet>
      )}
    </Card>
  )
}

function WaxForm({ data, onDone }: { data: ChainRotationData; onDone: (text: string) => void }) {
  const supplies = useApi<{ id: number; name: string; kind: string; unit: string }[]>('/consumables')
  const [ids, setIds] = useState<number[]>(data.dirty)
  const otherTicked = (list: number[]) => list.find((i) => i !== data.on) ?? null
  // until picked by hand, follow the ticks: when the chain on the bike is waxed, another ticked one goes on
  const [picked, setPicked] = useState<number | null | undefined>(undefined)
  const then = picked !== undefined ? picked : data.on !== null && ids.includes(data.on) ? otherTicked(ids) : null
  const [at, setAt] = useState(today())
  const [supply, setSupply] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opId] = useState(newOpId)
  const toggle = (id: number) => setIds(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])
  async function save() {
    setErr(null)
    setBusy(true)
    try {
      const r = await api.post<{ result: { text: string } }>(`/bikes/${data.bike_id}/chains/wax`, { component_ids: ids, at: afterRides(at), then_install: then, consumable_id: supply ? Number(supply) : null }, opId)
      onDone(r.result.text)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const onChain = data.chains.find((c) => c.component_id === data.on)
  return (
    <div className="form">
      <fieldset className="field">
        <legend className="field-label">Chains you hot waxed</legend>
        {data.chains
          .filter((c) => !['RETIRED', 'WORN'].includes(c.state))
          .map((c) => (
            <label key={c.component_id} className="check">
              <input type="checkbox" checked={ids.includes(c.component_id)} onChange={() => toggle(c.component_id)} /> {c.label}
              {c.mark ? ` (${c.mark})` : ''} <span className="muted small">· {STATE[c.state]?.[0] ?? c.state}</span>
            </label>
          ))}
      </fieldset>
      <Field label="Waxed on">
        <input type="date" value={at} onChange={(e) => setAt(e.target.value)} />
      </Field>
      <Field label="Then put on the bike">
        <select value={then ?? ''} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{onChain ? `Keep ${onChain.label} on` : 'Nothing for now'}</option>
          {data.chains
            .filter((c) => c.component_id !== data.on && (ids.includes(c.component_id) || c.state === 'READY_TO_INSTALL'))
            .map((c) => (
              <option key={c.component_id} value={c.component_id}>
                {c.label}
                {c.mark ? ` (${c.mark})` : ''}
              </option>
            ))}
        </select>
      </Field>
      {onChain && then !== null && <p className="small muted">{onChain.label} comes off first (stored, keeps its km) and is waxed with the others if ticked.</p>}
      <Field label="Wax used (optional)">
        <select value={supply} onChange={(e) => setSupply(e.target.value)}>
          <option value="">Not recorded</option>
          {supplies.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <FormError error={err} />
      <div className="form-actions">
        <button className="btn btn-primary" disabled={busy || ids.length === 0} onClick={save}>
          {busy ? 'Saving…' : `Hot wax ${ids.length} chain${ids.length === 1 ? '' : 's'}`}
        </button>
      </div>
    </div>
  )
}
