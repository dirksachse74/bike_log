import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { when } from '../format'
import { useApi } from '../hooks'
import { Card, ErrorBox, Field, FormError, Loading, Tag } from './ui'

interface StravaStatus {
  connected: boolean
  live_connection_verified: boolean
  last_error: string | null
  last_success_at: string | null
  alternative: string
  credentials: { client_id: string | null; secret_saved: boolean; tokens_saved: boolean; athlete_id: string | null; scope: string | null; env_file: string }
  job: { running: boolean; rescan?: boolean; page?: number; counts?: Record<string, number>; error?: string | null; finished_at?: string | null }
}

const COUNT_LABEL: Record<string, string> = { CREATED: 'new', UPDATED: 'updated', UNCHANGED: 'unchanged', SKIPPED_NOT_CYCLING: 'not cycling', BIKES_CREATED: 'bikes created', BIKES_LINKED: 'bikes linked' }
const countsText = (c?: Record<string, number>) =>
  Object.entries(c ?? {})
    .map(([k, v]) => `${v} ${COUNT_LABEL[k] ?? k.toLowerCase().replace(/_/g, ' ')}`)
    .join(', ') || 'nothing new'

// Everything for Strava without the command line: app details, connect (browser), sync, disconnect.
// The secret is sent once and never shown again; it is stored only in strava.env in the data folder.
export default function StravaSettings() {
  const st = useApi<StravaStatus>('/strava/status')
  const [params, setParams] = useSearchParams()
  const [f, setF] = useState({ client_id: '', client_secret: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const d = st.data
  const running = !!d?.job.running

  useEffect(() => {
    const result = params.get('strava')
    if (!result) return
    if (result === 'connected') setNotice(params.get('private') === '1' ? 'Strava connected, including private rides. Now press "Sync now".' : 'Strava connected. Private rides were not allowed, so only public rides will be imported. Now press "Sync now".')
    else setErr(params.get('message') ?? 'Strava connection failed')
    params.delete('strava')
    params.delete('message')
    params.delete('private')
    setParams(params, { replace: true })
  }, [params, setParams])
  useEffect(() => {
    if (d?.credentials.client_id && !f.client_id) setF((x) => ({ ...x, client_id: d.credentials.client_id ?? '' }))
  }, [d, f.client_id])
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(st.reload, 2000)
    return () => window.clearInterval(t)
  }, [running, st.reload])

  async function act(fn: () => Promise<unknown>, done?: string) {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      await fn()
      if (done) setNotice(done)
      st.reload()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function connect() {
    setBusy(true)
    setErr(null)
    try {
      const r = await api.post<{ authorize_url: string }>('/strava/connect')
      window.location.href = r.authorize_url
    } catch (e) {
      setErr((e as Error).message)
      setBusy(false)
    }
  }

  if (st.loading && !d) return <Card title="Strava"><Loading /></Card>
  if (st.error && !d) return <Card title="Strava"><ErrorBox error={st.error} onRetry={st.reload} /></Card>
  if (!d) return null
  const c = d.credentials
  const job = d.job
  return (
    <Card title="Strava">
      <p>
        {c.tokens_saved ? <Tag tone="good">Connected</Tag> : <Tag tone="warn">Not connected</Tag>}{' '}
        {d.last_success_at ? `Last successful sync: ${when(d.last_success_at)}.` : c.tokens_saved ? 'No sync yet.' : 'No successful sync with Strava yet.'}
      </p>
      {notice && <p className="notice">{notice}</p>}
      <FormError error={err} />

      {!c.tokens_saved && (
        <>
          <p className="small">
            <strong>1.</strong> On{' '}
            <a href="https://www.strava.com/settings/api" target="_blank" rel="noreferrer">
              strava.com/settings/api
            </a>{' '}
            create (or open) your API application and set <strong>Authorization Callback Domain</strong> to <code>localhost</code>. Copy the Client ID and Client Secret here.
          </p>
          <div className="row">
            <Field label="Client ID">
              <input inputMode="numeric" autoComplete="off" value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })} />
            </Field>
            <Field label="Client Secret" hint={c.secret_saved ? 'Saved. Leave empty to keep it.' : 'Stored only on this computer; never shown again.'}>
              <input type="password" autoComplete="new-password" value={f.client_secret} placeholder={c.secret_saved ? '•••••••• saved' : ''} onChange={(e) => setF({ ...f, client_secret: e.target.value })} />
            </Field>
          </div>
          <div className="form-actions">
            {c.secret_saved && (
              <button className="btn btn-small" disabled={busy} onClick={() => act(() => api.del('/strava/credentials'), 'Saved app details removed.').then(() => setF({ client_id: '', client_secret: '' }))}>
                Remove saved details
              </button>
            )}
            <button
              className="btn"
              disabled={busy || !f.client_id.trim() || (!c.secret_saved && !f.client_secret.trim())}
              onClick={() => act(() => api.put('/strava/credentials', { client_id: f.client_id, client_secret: f.client_secret || null }), 'Saved. Now connect with Strava.').then(() => setF((x) => ({ ...x, client_secret: '' })))}
            >
              Save app details
            </button>
          </div>
          <p className="small">
            <strong>2.</strong> Connect: Strava opens, you click <em>Authorize</em>, and you come back here.
          </p>
          <div className="form-actions">
            <button className="btn btn-primary" disabled={busy || !(c.client_id && c.secret_saved)} onClick={connect}>
              Connect with Strava
            </button>
          </div>
        </>
      )}

      {c.tokens_saved && (
        <>
          <p className="small muted">
            Strava athlete {c.athlete_id ?? '?'} · {c.scope?.includes('activity:read_all') ? 'private rides included' : 'public rides only'}. Rides are matched to bikes by their Strava gear; unknown gear creates or links a bike with the same name.
          </p>
          {running ? (
            <p className="notice">
              Syncing{job.rescan ? ' (re-reading everything)' : ''}… page {job.page ?? 0}: {countsText(job.counts)}
            </p>
          ) : (
            job.finished_at && (job.error ? <p className="small form-error">Sync failed: {job.error}</p> : <p className="small">Last sync: {countsText(job.counts)}.</p>)
          )}
          <div className="form-actions">
            <button
              className="btn btn-small"
              disabled={busy || running}
              onClick={() => {
                if (window.confirm('Disconnect Strava? Access is revoked and rides imported from the Strava API are deleted (a backup is made first). Rides you entered by hand or imported from CSV stay.'))
                  act(() => api.post<{ deleted_rides: number }>('/strava/disconnect').then((r) => setNotice(`Disconnected; ${r.deleted_rides} imported rides removed.`)))
              }}
            >
              Disconnect
            </button>
            <button className="btn" disabled={busy || running} onClick={() => act(() => api.post('/strava/sync', { rescan: true }))}>
              Re-read all since start date
            </button>
            <button className="btn btn-primary" disabled={busy || running} onClick={() => act(() => api.post('/strava/sync', { rescan: false }))}>
              {running ? 'Syncing…' : 'Sync now'}
            </button>
          </div>
        </>
      )}
      {d.last_error && !running && !job.finished_at && <p className="small form-error">Last attempt failed: {d.last_error}</p>}
      <p className="small muted">
        Not yet tested against the real Strava; tell me if anything fails. {d.alternative} The app works fully without Strava.
      </p>
    </Card>
  )
}
