import { Link } from 'react-router-dom'
import { km, when } from '../format'
import { useApi } from '../hooks'
import { Empty, ErrorBox, Loading, Tag } from './ui'

// Rides → Punctures (DECISIONS 117): every flat (a "Flat tire" incident, one row per wheel) with the tube and
// tire that were on, and per tube / tire model the punctures and km per puncture. Computed, nothing stored.

interface PunctureRow {
  group: string
  on: string
  ride_id: number | null
  ride: string | null
  bike: string | null
  wheel: string
  damage: string
  tube_id: number | null
  tube_model: string | null
  tube_inferred: boolean
  tire_id: number | null
  tire_model: string
  conditions: string | null
  fixed: string | null
}

interface ModelRow {
  model: string
  punctures: number
  parts: number
  km: number | null
  km_per_puncture: number | null
}

interface Count {
  name: string
  punctures: number
}

interface Report {
  total: number
  rows: PunctureRow[]
  by_tube: ModelRow[]
  by_tire: ModelRow[]
  by_bike: Count[]
  by_wheel: Count[]
  by_conditions: Count[]
  by_damage: Count[]
}

function ModelTable({ title, rows, what }: { title: string; rows: ModelRow[]; what: string }) {
  return (
    <details className="life-type punct-models" data-what={what} open>
      <summary>
        <strong>{title}</strong>
      </summary>
      {rows.length === 0 ? (
        <p className="small muted">None recorded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Model</th>
              <th className="num">Punctures</th>
              <th className="num">Km ridden</th>
              <th className="num">Km per puncture</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.model}>
                <td>
                  {m.model}
                  {m.parts > 0 && (
                    <div className="small muted" title={`The km ridden are the km of these ${what}s together`}>
                      {m.parts} {m.parts === 1 ? what : `${what}s`} of this model in your parts
                    </div>
                  )}
                </td>
                <td className="num">{m.punctures}</td>
                <td className="num">{m.km != null ? km(m.km, 0) : '–'}</td>
                <td className="num">{m.km_per_puncture != null ? km(m.km_per_puncture, 0) : m.punctures === 0 && m.km ? 'none yet' : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  )
}

const counts = (c: Count[]) => c.map((x) => `${x.name} ${x.punctures}`).join(' · ')

export default function Punctures() {
  const { data, error, loading, reload } = useApi<Report>('/reports/punctures')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data || data.total === 0)
    return (
      <Empty title="No punctures logged">
        Log a puncture on the ride it happened: Rides → open the ride → Add incident → Flat tire, then say per wheel whether it was the tube only or the tube and the tire. Fix
        brings in the new tube (from stock, a spare or patched). The statistics show up here.
      </Empty>
    )
  return (
    <div className="punctures">
      <p className="small muted">
        Every flat logged on a ride (Add incident → Flat tire), per wheel. Km per puncture = km all your tubes (tires) of that model have done ÷ their punctures. Tubes taken from
        stock have no own record: a flat on such a tube counts for the tube the last fix on that wheel put in (marked "from the last fix").
      </p>
      <div className="stats">
        <div>
          <span className="stat">{data.total}</span>
          <span className="muted small">{data.total === 1 ? "puncture" : "punctures"}</span>
        </div>
        <div>
          <span className="small">{counts(data.by_wheel)}</span>
          <span className="muted small">by wheel</span>
        </div>
        <div>
          <span className="small">{counts(data.by_conditions)}</span>
          <span className="muted small">wet or dry</span>
        </div>
        <div>
          <span className="small">{counts(data.by_bike)}</span>
          <span className="muted small">by bike</span>
        </div>
      </div>
      <ModelTable title="By inner tube" rows={data.by_tube} what="tube" />
      <ModelTable title="By tire" rows={data.by_tire} what="tire" />
      <details className="life-type punct-list">
        <summary>
          <strong>All punctures</strong> <span className="muted small">{data.total}</span>
        </summary>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Bike · wheel</th>
              <th>Tube</th>
              <th>Tire</th>
              <th>Damage</th>
              <th>Fixed</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={`${r.group}-${r.wheel}`}>
                <td>
                  {r.ride_id ? <Link to={`/rides?open=${r.ride_id}`}>{when(r.on)}</Link> : when(r.on)}
                  {r.conditions && <div className="small muted">{r.conditions === 'WET' ? 'wet' : 'dry'}</div>}
                </td>
                <td>
                  {r.bike ?? '–'} · {r.wheel}
                </td>
                <td>
                  {r.tube_id ? <Link to={`/inventory/${r.tube_id}`}>{r.tube_model}</Link> : (r.tube_model ?? '–')}
                  {r.tube_inferred && <div className="small muted">from the last fix</div>}
                </td>
                <td>{r.tire_id ? <Link to={`/inventory/${r.tire_id}`}>{r.tire_model}</Link> : r.tire_model}</td>
                <td>{r.damage}</td>
                <td className="small">{r.fixed ?? <Tag tone="warn">not yet</Tag>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
