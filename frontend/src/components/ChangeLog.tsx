import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { when } from '../format'
import { useApi } from '../hooks'
import type { ChangeRow } from '../types'
import { Card, Empty, ErrorBox, Loading, Tag } from './ui'

const ACTION_LABEL: Record<string, string> = {
  CREATED: 'added',
  CHANGED: 'changed',
  INSTALLED: 'installed',
  REMOVED: 'removed',
  REINSTATED: 'removal undone',
  VOIDED: 'entry voided',
  DELETED: 'deleted',
}
const via = (v: string | null) => (v ? v.replace(/[._]/g, ' ') : null)

// Every change to a bike or part, newest first: what changed (old → new), when and who/what made it.
// Written automatically by the backend; it cannot be edited. Dated notes belong in the journal.
export default function ChangeLog({ bikeId, componentId, refresh, className = '' }: { bikeId?: number; componentId?: number; refresh?: unknown; className?: string }) {
  const { data, error, loading, reload } = useApi<ChangeRow[]>(`/changes?${bikeId ? `bike_id=${bikeId}` : `component_id=${componentId}`}`)
  const [all, setAll] = useState(false)
  useEffect(() => {
    if (refresh !== undefined) reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh])
  const rows = data ? (all ? data : data.slice(0, 12)) : []
  return (
    <Card title="Change log" className={className}>
      {loading && !data && <Loading what="Loading changes" />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && data.length === 0 && <Empty title="No changes recorded yet">Changes are recorded from this version on.</Empty>}
      {rows.length > 0 && (
        <table className="table changelog">
          <thead>
            <tr>
              <th>When</th>
              {bikeId !== undefined && <th>Part</th>}
              <th>What</th>
              <th>Change</th>
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="nowrap">{when(r.changed_at)}</td>
                {bikeId !== undefined && <td>{r.component_id ? <Link to={`/inventory/${r.component_id}`}>{r.component}</Link> : <span className="muted">bike</span>}</td>}
                <td>
                  <Tag>{ACTION_LABEL[r.action] ?? r.action.toLowerCase()}</Tag> {r.field}
                </td>
                <td>
                  {r.old_value !== null && r.new_value !== null ? (
                    <>
                      <span className="muted">{r.old_value}</span> → {r.new_value}
                    </>
                  ) : (
                    (r.new_value ?? (r.old_value !== null && r.action === 'CHANGED' ? <><span className="muted">{r.old_value}</span> → —</> : r.old_value))
                  )}
                </td>
                <td className="small muted">
                  {r.who}
                  {via(r.via) && ` · ${via(r.via)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.length > 12 && (
        <div className="form-actions">
          <button className="btn btn-small" onClick={() => setAll(!all)}>
            {all ? 'Show recent only' : `Show all ${data.length}`}
          </button>
        </div>
      )}
    </Card>
  )
}
