import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newOpId } from '../api'
import { today, when } from '../format'
import { useApi } from '../hooks'
import type { JournalRow } from '../types'
import { Card, Empty, ErrorBox, FormError, Loading, Tag } from './ui'

// Dated notes on a bike or a part. Notes written on maintenance entries show up here too (read-only),
// so there is one place to read what happened.
export default function Journal({ bikeId, componentId, className = '' }: { bikeId?: number; componentId?: number; className?: string }) {
  const query = bikeId ? `bike_id=${bikeId}` : `component_id=${componentId}`
  const { data, error, loading, reload } = useApi<JournalRow[]>(`/journal?${query}`)
  const [f, setF] = useState({ on: today(), kind: 'NOTE', text: '' })
  const [opId, setOpId] = useState(newOpId)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [editing, setEditing] = useState<{ id: number; text: string; on: string } | null>(null)

  async function add() {
    setBusy(true)
    setErr(null)
    try {
      await api.post('/journal', { ...f, bike_id: bikeId ?? null, component_id: componentId ?? null }, opId)
      setF({ on: today(), kind: 'NOTE', text: '' })
      setOpId(newOpId())
      reload()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function act(fn: () => Promise<unknown>) {
    setErr(null)
    try {
      await fn()
      setEditing(null)
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <Card title="Journal" className={className}>
      <div className="journal-add">
        <input type="date" aria-label="Journal date" value={f.on} onChange={(e) => setF({ ...f, on: e.target.value })} />
        <select aria-label="Journal kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="NOTE">Note</option>
          <option value="ISSUE">Issue</option>
        </select>
        <textarea aria-label="Journal note" rows={2} value={f.text} placeholder="What happened? e.g. creak when climbing out of the saddle" onChange={(e) => setF({ ...f, text: e.target.value })} />
        <button className="btn btn-primary" disabled={busy || !f.text.trim()} onClick={add}>
          {busy ? 'Saving…' : 'Add note'}
        </button>
      </div>
      <FormError error={err} />
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && data.length === 0 && <Empty title="No notes yet">Notes and issues you add here are kept with their date.</Empty>}
      {data && data.length > 0 && (
        <ul className="list journal">
          {data.map((r) => (
            <li key={`${r.source}${r.id}`}>
              <span className="muted small journal-date">{when(r.on)}</span>
              <span className="journal-text">
                {r.kind === 'ISSUE' && <Tag tone={r.open_issue ? 'warn' : 'good'}>{r.open_issue ? 'open issue' : `resolved ${when(r.resolved_on)}`}</Tag>}
                {r.kind === 'MAINTENANCE' && <Tag tone="info">maintenance</Tag>}{' '}
                {bikeId && r.component_label && r.component_id && (
                  <>
                    <Link to={`/inventory/${r.component_id}`}>{r.component_label}</Link>:{' '}
                  </>
                )}
                {editing?.id === r.id && r.source === 'JOURNAL' ? (
                  <span className="journal-edit">
                    <input type="date" aria-label="Edit date" value={editing.on} onChange={(e) => setEditing({ ...editing, on: e.target.value })} />
                    <textarea aria-label="Edit note" rows={2} value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} />
                    <button className="btn btn-small btn-primary" onClick={() => act(() => api.patch(`/journal/${r.id}`, { text: editing.text, on: editing.on }))}>
                      Save
                    </button>
                    <button className="btn btn-small" onClick={() => setEditing(null)}>
                      Cancel
                    </button>
                  </span>
                ) : (
                  <span className="pre">{r.text}</span>
                )}
                {r.edited && <span className="muted small"> (edited)</span>}
              </span>
              {r.source === 'JOURNAL' && editing?.id !== r.id && (
                <span className="row-actions">
                  {r.open_issue && (
                    <button className="btn btn-small" onClick={() => act(() => api.patch(`/journal/${r.id}`, { resolved_on: today() }))}>
                      Resolved
                    </button>
                  )}
                  <button className="btn btn-small" onClick={() => setEditing({ id: r.id, text: r.text, on: r.on })}>
                    Edit
                  </button>
                  <button
                    className="btn btn-small"
                    onClick={() => {
                      if (window.confirm('Remove this note? It stays in the history as removed.')) act(() => api.post(`/journal/${r.id}/void`, { reason: 'removed by user' }))
                    }}
                  >
                    Remove
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
