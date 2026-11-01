import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../context'
import { Card, Field, FormError } from './ui'

interface ResetResult {
  backup: string | null
  backup_path: string | null
  strava: string
}

// Empty database for a fresh start. A backup of everything is written first and kept (never pruned),
// so the reset can be undone with "Restore" here or in the backup list.
export default function FreshStart({ onChanged }: { onChanged: () => void }) {
  const { reloadMeta, toast } = useApp()
  const [confirm, setConfirm] = useState('')
  const [clearStrava, setClearStrava] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<ResetResult | null>(null)
  const [params] = useSearchParams()
  const ref = useRef<HTMLDivElement>(null)
  // the "Sample data" banner links here
  useEffect(() => {
    if (params.get('section') === 'fresh-start') ref.current?.scrollIntoView({ block: 'start' })
  }, [params])

  async function reset() {
    setBusy(true)
    setErr(null)
    try {
      const r = await api.post<ResetResult>('/admin/reset', { confirm, clear_strava: clearStrava })
      setDone(r)
      setConfirm('')
      reloadMeta()
      onChanged()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function undo() {
    if (!done?.backup) return
    setBusy(true)
    setErr(null)
    try {
      await api.post(`/backups/${encodeURIComponent(done.backup)}/restore`)
      toast('Fresh start undone: your data is back.')
      setDone(null)
      reloadMeta()
      onChanged()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div ref={ref} id="fresh-start">
      <Card title="Fresh start">
      {done ? (
        <div className="notice">
          <p>
            <strong>The database is empty now.</strong> Everything from before is in the backup <code>{done.backup_path}</code>; it is kept and never deleted
            automatically.
          </p>
          <p className="small">Strava: {done.strava}{done.strava === 'kept (connected)' ? '. Press Sync in the Strava section to import your rides again.' : '.'}</p>
          <div className="form-actions">
            <button className="btn" disabled={busy} onClick={undo}>
              Undo: restore that backup
            </button>
          </div>
        </div>
      ) : (
        <div className="form">
          <p className="small">
            Start over with an empty database: no bikes, parts, rides or maintenance. Settings and the default service rules start fresh as well. A full backup is
            made first and kept, so you can go back with <em>Restore</em>.
          </p>
          <label className="check">
            <input type="checkbox" checked={clearStrava} onChange={(e) => setClearStrava(e.target.checked)} /> Also clear the Strava connection (app details and login)
          </label>
          <p className="small muted">
            {clearStrava ? 'You will have to enter the Strava app details and connect again.' : 'Strava stays connected; one Sync fills the new database with your rides.'}
          </p>
          <Field label="Type RESET to confirm">
            <input aria-label="Type RESET to confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
          </Field>
          <FormError error={err} />
          <div className="form-actions">
            <button className="btn btn-danger" disabled={busy || confirm.trim() !== 'RESET'} onClick={reset}>
              {busy ? 'Working…' : 'Reset database'}
            </button>
          </div>
        </div>
      )}
      {done && <FormError error={err} />}
      </Card>
    </div>
  )
}
