import { Link } from 'react-router-dom'
import { km, when } from '../format'
import { useApi } from '../hooks'
import { Empty, ErrorBox, Loading, Tag } from './ui'

interface LifeRow {
  component_id: number
  label: string
  product: string | null
  bikes: string[]
  first_installed: string | null
  ended: string | null
  months: number | null
  km: number
  hours: number
  rides: number
  certainty: string
  is_minimum: boolean
  estimated: boolean
  why: string | null
}

interface Average {
  count: number
  avg_km: number | null
  min_km: number | null
  max_km: number | null
  avg_hours: number | null
  avg_months: number | null
  estimated: boolean
  minimum: boolean
}

interface LifeType {
  code: string
  name: string
  finished: LifeRow[]
  in_use: LifeRow[]
  products: (Average & { product_id: number | null; product: string })[]
  overall: Average | null
}

// "≈" for estimates (km from before, uncertain rides), "≥" when the earlier history is unknown
function Km({ v, estimated, minimum }: { v: number | null; estimated: boolean; minimum: boolean }) {
  if (v === null) return <>–</>
  return (
    <span title={minimum ? 'At least: the part was used before Bike Log and that is unknown' : estimated ? 'Estimated: includes km from before or rides with an uncertain bike' : 'Known'}>
      {minimum ? '≥ ' : estimated ? '≈ ' : ''}
      {km(v, 0)}
    </span>
  )
}

const months = (m: number | null) => (m === null ? '–' : `${m.toLocaleString(undefined, { maximumFractionDigits: 1 })} mo`)

// Inventory → Part life: how long parts lasted, per type and product. Computed, nothing stored.
export default function PartLife() {
  const { data, error, loading, reload } = useApi<{ types: LifeType[] }>('/reports/part-life')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data || data.types.length === 0) return <Empty title="No part history yet">Once parts have been on a bike, their life shows here.</Empty>
  return (
    <>
      <p className="small muted">
        How long your parts lasted: every part that is out of use for good (worn out, retired, sold, returned under warranty) with its lifetime, and an average per product. ≈ marks estimates (km from before Bike Log, rides with an uncertain bike), ≥ a minimum (earlier use unknown). Parts still in use are listed apart and never count in an average.
      </p>
      {data.types.map((t) => (
        <details key={t.code} className="life-type" data-type={t.code}>
          <summary>
            <strong>{t.name}</strong>{' '}
            <span className="muted small">
              {t.finished.length} finished
              {t.overall?.avg_km != null && (
                <>
                  {' · average '}
                  <Km v={t.overall.avg_km} estimated={t.overall.estimated} minimum={t.overall.minimum} />
                </>
              )}
              {t.in_use.length > 0 && ` · ${t.in_use.length} in use`}
            </span>
          </summary>
          {t.products.length > 0 && (
            <>
              <h4>Per product</h4>
              <table className="table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th className="num">Parts</th>
                    <th className="num">Average</th>
                    <th className="num">Range</th>
                    <th className="num">Hours</th>
                    <th className="num">Months</th>
                  </tr>
                </thead>
                <tbody>
                  {t.products.map((p) => (
                    <tr key={p.product}>
                      <td>{p.product}</td>
                      <td className="num">{p.count}</td>
                      <td className="num">
                        <Km v={p.avg_km} estimated={p.estimated} minimum={p.minimum} />
                      </td>
                      <td className="num">{p.count > 1 ? `${km(p.min_km, 0)}–${km(p.max_km, 0)}` : '–'}</td>
                      <td className="num">{p.avg_hours ?? '–'}</td>
                      <td className="num">{months(p.avg_months)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {t.finished.length > 0 && (
            <>
              <h4>Finished parts</h4>
              <table className="table">
                <thead>
                  <tr>
                    <th>Part</th>
                    <th className="num">Lifetime</th>
                    <th className="num">Hours</th>
                    <th className="num">In use</th>
                    <th>Bikes</th>
                    <th>Why it went</th>
                  </tr>
                </thead>
                <tbody>
                  {t.finished.map((r) => (
                    <tr key={r.component_id}>
                      <td>
                        <Link to={`/inventory/${r.component_id}`}>{r.label}</Link>
                        {r.product && <div className="small muted">{r.product}</div>}
                      </td>
                      <td className="num">
                        <Km v={r.km} estimated={r.estimated} minimum={r.is_minimum} />
                      </td>
                      <td className="num">{r.hours || '–'}</td>
                      <td className="num">
                        {months(r.months)}
                        <div className="small muted">
                          {when(r.first_installed)} – {when(r.ended)}
                        </div>
                      </td>
                      <td>{r.bikes.join(', ') || '–'}</td>
                      <td>{r.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {t.in_use.length > 0 && (
            <>
              <h4>Still in use</h4>
              <ul className="list">
                {t.in_use.map((r) => (
                  <li key={r.component_id} className="small">
                    <Link to={`/inventory/${r.component_id}`}>{r.label}</Link> · <Km v={r.km} estimated={r.estimated} minimum={r.is_minimum} /> so far
                    {r.months !== null && ` · ${months(r.months)}`}
                    {r.bikes.length > 0 && ` · ${r.bikes.join(', ')}`}
                    {r.estimated && (
                      <>
                        {' '}
                        <Tag>{r.is_minimum ? 'minimum' : 'estimated'}</Tag>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </details>
      ))}
    </>
  )
}
