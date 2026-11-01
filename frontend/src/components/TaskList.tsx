import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { today } from '../format'
import type { Task } from '../types'
import LogMaintenance from './LogMaintenance'
import { Empty, Sheet, StatusBadge } from './ui'

/** Due tasks with the reason for each, plus one-tap log and snooze (snoozing records no maintenance). */
export default function TaskList({ tasks, onChange, emptyText = 'Nothing due by recorded usage.' }: { tasks: Task[]; onChange: () => void; emptyText?: string }) {
  const { toast, meta } = useApp()
  const [logging, setLogging] = useState<Task | null>(null)
  const [error, setError] = useState<string | null>(null)
  if (!tasks.length) return <Empty title={emptyText}>{meta.safety_note}</Empty>

  async function snooze(t: Task, body: { until_date?: string; extra_km?: number }) {
    try {
      const who = t.component_id ? { component_id: t.component_id } : { bike_id: t.bike_id }
      await api.post('/maintenance/snooze', { ...who, rule_code: t.rule_code, ...body })
      toast(`Snoozed "${t.name}" for ${t.component ?? t.bike}. No maintenance recorded.`)
      onChange()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function swap(t: Task) {
    if (!t.rotation?.to) return
    try {
      const r = await api.post<{ result: { text: string } }>(`/bikes/${t.rotation.bike_id}/chains/swap`, { to_component_id: t.rotation.to, at: new Date().toISOString() }, newOpId())
      toast(r.result.text)
      onChange()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function unsnooze(t: Task) {
    await api.del(`/maintenance/snooze/${t.snooze_id}`)
    onChange()
  }
  // from the local "today" (the app's timezone), not the UTC date
  const inDays = (n: number) => new Date(Date.parse(`${today()}T12:00:00Z`) + n * 864e5).toISOString().slice(0, 10)

  return (
    <>
      {error && <div className="form-error">{error}</div>}
      <ul className="tasks">
        {tasks.map((t) => (
          <li key={`${t.component_id ?? 'bike' + t.bike_id}-${t.rule_code}`} className={`task task-${t.status.toLowerCase()}`}>
            <div className="task-main">
              <StatusBadge status={t.status} />
              <div>
                <div className="task-title">
                  {t.component_id ? (
                    <>
                      {t.name} · <Link to={`/inventory/${t.component_id}`}>{t.component}</Link>
                      {t.bike && <span className="muted"> on {t.bike}</span>}
                    </>
                  ) : (
                    <>
                      {t.name} · <Link to={`/bikes/${t.bike_id}`}>{t.bike}</Link> <span className="muted">(whole bike)</span>
                    </>
                  )}
                </div>
                <div className="task-why">{t.explanation}</div>
                {t.forecast && !['DUE', 'OVERDUE'].includes(t.status) && <div className="task-forecast small muted">{t.forecast.text}</div>}
              </div>
            </div>
            <div className="task-actions">
              {t.rotation?.to && (
                <button className="btn btn-small btn-primary" onClick={() => swap(t)}>
                  Swap to {t.rotation.to_label}
                </button>
              )}
              {t.rotation?.kind === 'WAX' && (
                <Link className="btn btn-small btn-primary" to={`/bikes/${t.rotation.bike_id}`}>
                  Wax chains
                </Link>
              )}
              {!t.rotation && (t.status !== 'ATTENTION' || !t.component_id) && t.status !== 'NOT_APPLICABLE' && (
                <button className="btn btn-small btn-primary" onClick={() => setLogging(t)}>
                  Log done
                </button>
              )}
              {t.status === 'SNOOZED' ? (
                <button className="btn btn-small" onClick={() => unsnooze(t)}>
                  Unsnooze
                </button>
              ) : (
                ['DUE', 'OVERDUE', 'DUE_SOON'].includes(t.status) && (
                  <>
                    <button className="btn btn-small" onClick={() => snooze(t, { until_date: inDays(7) })}>
                      Snooze 7 days
                    </button>
                    {t.used_km !== undefined && t.used_km !== null && (
                      <button className="btn btn-small" onClick={() => snooze(t, { extra_km: 100 })}>
                        +100 km
                      </button>
                    )}
                  </>
                )
              )}
            </div>
          </li>
        ))}
      </ul>
      {logging && (
        <Sheet title={`Log: ${logging.name}`} onClose={() => setLogging(null)}>
          <LogMaintenance
            componentId={logging.component_id}
            bikeId={logging.component_id ? null : logging.bike_id}
            actionCode={logging.action_code}
            onDone={(msg) => {
              setLogging(null)
              toast(msg)
              onChange()
            }}
          />
        </Sheet>
      )}
    </>
  )
}
