import { useRef, useState } from 'react'
import { api } from '../api'
import Diagnostics from '../components/Diagnostics'
import FreshStart from '../components/FreshStart'
import StravaSettings from '../components/StravaSettings'
import VersionInfo from '../components/VersionInfo'
import { Card, Field, FormError, Tag } from '../components/ui'
import { useApp } from '../context'
import { when } from '../format'
import { useApi } from '../hooks'

interface ImportResult {
  batch_id: number
  source_kind: string
  resumed: boolean
  rows: number
  counts: Record<string, number>
  errors: { row: number; error: string }[]
  unknown_bikes?: Record<string, number>
}

interface Batch {
  id: number
  source_kind: string
  file_name: string | null
  status: string
  rows_total: number | null
  cursor_row: number
  counts: Record<string, unknown>
  started_at: string
  finished_at: string | null
}

export default function SettingsPage() {
  const { meta, reloadMeta, toast } = useApp()
  const [f, setF] = useState({ timezone: meta.settings.timezone, import_start_date: meta.settings.import_start_date, trainer_profile_for_virtual: meta.settings.trainer_profile_for_virtual, default_tire_setup: meta.settings.default_tire_setup ?? 'TUBE' })
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const batches = useApi<Batch[]>('/imports')
  const backups = useApi<{ directory: string; backup_dir: string; backups: { name: string; size: number; kept: boolean }[]; exports: { name: string; size: number }[] }>('/backups')
  const fileRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [importErr, setImportErr] = useState<string | null>(null)

  async function save() {
    setSaving(true)
    setErr(null)
    try {
      await api.patch('/settings', f)
      reloadMeta()
      toast('Settings saved.')
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }
  async function upload() {
    const file = fileRef.current?.files?.[0]
    if (!file) return setImportErr('Choose a CSV file first.')
    setImporting(true)
    setImportErr(null)
    setResult(null)
    try {
      setResult(await api.upload<ImportResult>(`/imports/csv?file_name=${encodeURIComponent(file.name)}`, file))
      batches.reload()
    } catch (e) {
      setImportErr((e as Error).message)
      batches.reload()
    } finally {
      setImporting(false)
    }
  }
  async function restore(name: string) {
    if (!window.confirm(`Replace all current data with the backup ${name}? A backup of the current data is made first, so this can be undone.`)) return
    try {
      await api.post(`/backups/${encodeURIComponent(name)}/restore`)
      toast(`Restored ${name}.`)
      reloadMeta()
      backups.reload()
    } catch (e) {
      toast((e as Error).message)
    }
  }
  async function backupNow(kind: 'backups' | 'exports') {
    try {
      const r = await api.post<{ name: string }>(`/${kind}`)
      toast(`${kind === 'backups' ? 'Backup' : 'Export'} written: ${r.name}`)
      backups.reload()
    } catch (e) {
      toast((e as Error).message)
    }
  }
  return (
    <div className="grid">
      <Card title="Settings">
        <div className="form">
          <Field label="Timezone" hint="Dates are shown in this timezone. Changing it recomputes date-only boundaries.">
            <input value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.target.value })} />
          </Field>
          <Field label="Import start date" hint="Imported rides before this local date are skipped. Empty = import everything.">
            <input type="date" value={f.import_start_date} onChange={(e) => setF({ ...f, import_start_date: e.target.value })} />
          </Field>
          <Field label="Default tire setup" hint="Used for wheels where tube or tubeless is not set, so tubeless reminders (sealant, valves) stay off for tubes.">
            <select aria-label="Default tire setup" value={f.default_tire_setup} onChange={(e) => setF({ ...f, default_tire_setup: e.target.value })}>
              {meta.tire_setups.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Setup for indoor (Virtual) rides">
            <select value={f.trainer_profile_for_virtual} onChange={(e) => setF({ ...f, trainer_profile_for_virtual: e.target.value })}>
              <option value="">Treat like outdoor</option>
              {meta.profiles
                .filter((p) => p.kind === 'TRAINER')
                .map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
            </select>
          </Field>
          {meta.profiles
            .filter((p) => p.kind === 'TRAINER')
            .map((p) => (
              <p key={p.code} className="small muted">
                {p.name}: excludes {[...p.excluded_slots, ...p.excluded_types].map((s) => s.replace(/_/g, ' ').toLowerCase()).join(', ')}. {p.notes}
              </p>
            ))}
          <FormError error={err} />
          <div className="form-actions">
            <button className="btn btn-primary" disabled={saving} onClick={save}>
              Save settings
            </button>
          </div>
        </div>
      </Card>
      <Card title="Import rides (CSV)">
        <p className="small">
          Bike Log CSV: columns <code>source_id, date, distance_km</code> (or <code>distance_mi</code>), optional <code>duration_min, name, bike, sport_type, trainer</code>.{' '}
          <a href="./api/imports/template">Download a template</a>. Strava's own export (<em>Download your data → activities.csv</em>) is recognised too. Re-importing a file never duplicates rides; your corrections and removals are kept.
        </p>
        <div className="row">
          <input ref={fileRef} type="file" accept=".csv,text/csv" aria-label="CSV file" />
          <button className="btn btn-primary" disabled={importing} onClick={upload}>
            {importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        <FormError error={importErr} />
        {result && (
          <div className="notice">
            {result.resumed && 'Resumed an interrupted import. '}
            {Object.entries(result.counts)
              .map(([k, v]) => `${v} ${k.replace(/_/g, ' ').toLowerCase()}`)
              .join(', ') || 'Nothing to import.'}
            {Object.keys(result.unknown_bikes ?? {}).length > 0 && (
              <p>
                No bike with this name, so these rides have no bike yet (the name is kept on each ride; add the
                bike or assign the rides on the Rides page):{' '}
                {Object.entries(result.unknown_bikes ?? {})
                  .map(([name, n]) => `${name} (${n} ${n === 1 ? 'ride' : 'rides'})`)
                  .join(', ')}
              </p>
            )}
            {result.errors.length > 0 && (
              <ul>
                {result.errors.slice(0, 10).map((e) => (
                  <li key={e.row}>
                    Row {e.row}: {e.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {batches.data && batches.data.length > 0 && (
          <ul className="list">
            {batches.data.map((b) => (
              <li key={b.id}>
                <span>{when(b.started_at)}</span>
                <span>{b.file_name ?? b.source_kind}</span>
                <Tag tone={b.status === 'COMPLETED' ? 'good' : b.status === 'FAILED' ? 'bad' : 'warn'}>{b.status.toLowerCase()}</Tag>
                <span className="small muted">
                  {b.cursor_row}/{b.rows_total ?? '?'} rows
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <StravaSettings />
      <Card title="Backups and export">
        {backups.data && (
          <>
            <p className="small">
              Your data is stored in <code>{backups.data.directory}</code>, outside the program folder. A backup is made automatically before every upgrade and once a day.
            </p>
            <div className="form-actions">
              <button className="btn" onClick={() => backupNow('backups')}>
                Back up now
              </button>
              <button className="btn" onClick={() => backupNow('exports')}>
                Full export (zip)
              </button>
            </div>
            <ul className="list small">
              {backups.data.exports.slice(0, 3).map((e) => (
                <li key={e.name}>
                  <a href={`./api/exports/${e.name}`}>{e.name}</a>
                </li>
              ))}
              {backups.data.backups
                .filter((b, i) => i < 5 || b.kept)
                .map((b) => (
                  <li key={b.name}>
                    {b.name} <span className="muted">({Math.round(b.size / 1024)} KB{b.kept ? ', kept' : ''})</span>
                    <button className="btn btn-small" aria-label={`Restore ${b.name}`} onClick={() => restore(b.name)}>
                      Restore
                    </button>
                  </li>
                ))}
            </ul>
          </>
        )}
        <VersionInfo />
      </Card>
      <FreshStart onChanged={backups.reload} />
      <Diagnostics />
    </div>
  )
}
