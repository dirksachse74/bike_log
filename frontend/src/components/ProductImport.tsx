import { useState } from 'react'
import { api, newOpId } from '../api'
import { useApp } from '../context'
import { Field, FormError, Tag } from './ui'

interface Report {
  ok: boolean
  dry_run: boolean
  errors: string[]
  warnings: string[]
  counts: { CREATED: number; UPDATED: number; UNCHANGED: number; ITEMS_CREATED: number; ITEMS_EXISTING: number }
  products: { at: string; component_type: string; maker: string; model: string; status: string; changed: string[]; items: { label: string; status: string }[] }[]
}

interface FileResult {
  name: string
  report?: Report
  error?: string
}

// Product JSON files from scripts (e.g. scrapers). Each file is checked first; nothing is written until
// "Import". A file with any error is skipped as a whole. The templates are one schema + example per type.
export default function ProductImport({ onDone }: { onDone: (msg: string) => void }) {
  const { meta } = useApp()
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<FileResult[] | null>(null)
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [type, setType] = useState('CHAIN')

  async function run(dry: boolean) {
    setBusy(true)
    setError(null)
    const out: FileResult[] = []
    const valid = new Set(results?.filter((r) => r.report?.ok).map((r) => r.name))
    for (const f of dry ? files : files.filter((x) => valid.has(x.name))) {
      try {
        const text = await f.text()
        const report = await api.post<Report>(`/imports/products${dry ? '?dry_run=true' : ''}`, JSON.parse(text), dry ? undefined : newOpId())
        out.push({ name: f.name, report })
      } catch (e) {
        out.push({ name: f.name, error: e instanceof SyntaxError ? `Not valid JSON: ${e.message}` : (e as Error).message })
      }
    }
    setResults(out)
    setBusy(false)
    if (dry) setChecked(true)
    else {
      const ok = out.filter((r) => r.report?.ok)
      const c = (k: keyof Report['counts']) => ok.reduce((s, r) => s + (r.report?.counts[k] ?? 0), 0)
      onDone(`${ok.length} of ${out.length} file${out.length === 1 ? '' : 's'} imported: ${c('CREATED')} new, ${c('UPDATED')} updated products, ${c('ITEMS_CREATED')} new parts.`)
    }
  }
  const good = results?.filter((r) => r.report?.ok).length ?? 0
  return (
    <div className="form">
      <p className="small muted">
        Import product data made by a script, for example a scraper. One file can hold one product or a list. Importing the same file again changes nothing; changed data updates the
        product. Parts listed under <code>items</code> are added as spares.
      </p>
      <Field label="JSON files">
        <input
          type="file"
          accept=".json,application/json"
          multiple
          aria-label="JSON files"
          onChange={(e) => {
            setFiles(Array.from(e.target.files ?? []))
            setResults(null)
            setChecked(false)
          }}
        />
      </Field>
      {results && (
        <ul className="list import-results">
          {results.map((r) => (
            <li key={r.name}>
              <span>
                <strong>{r.name}</strong>{' '}
                {r.error ? (
                  <Tag tone="bad">not readable</Tag>
                ) : r.report?.ok ? (
                  <Tag tone="good">
                    {r.report.dry_run ? 'ready' : 'imported'}: {r.report.counts.CREATED} new · {r.report.counts.UPDATED} updated · {r.report.counts.UNCHANGED} unchanged
                    {r.report.counts.ITEMS_CREATED ? ` · ${r.report.counts.ITEMS_CREATED} new parts` : ''}
                  </Tag>
                ) : (
                  <Tag tone="bad">{r.report?.errors.length} error{r.report?.errors.length === 1 ? '' : 's'}, nothing will be imported</Tag>
                )}
                {r.error && <span className="small"> {r.error}</span>}
                {r.report && (
                  <span className="small import-lines">
                    {r.report.errors.map((e) => (
                      <span key={e} className="bad-text">
                        {e}
                      </span>
                    ))}
                    {r.report.ok &&
                      r.report.products.map((p) => (
                        <span key={p.at}>
                          {p.maker} {p.model}: {p.status.toLowerCase()}
                          {p.changed.length ? ` (${p.changed.join(', ')})` : ''}
                          {p.items.length ? ` · parts: ${p.items.map((i) => `${i.label} ${i.status === 'EXISTS' ? '(exists)' : '(new)'}`).join(', ')}` : ''}
                        </span>
                      ))}
                    {r.report.warnings.map((w) => (
                      <span key={w} className="muted">
                        {w}
                      </span>
                    ))}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <FormError error={error} />
      <div className="form-actions">
        <button className="btn" disabled={busy || files.length === 0} onClick={() => run(true)}>
          {busy && !checked ? 'Checking…' : 'Check files'}
        </button>
        <button className="btn btn-primary" disabled={busy || !checked || good === 0} onClick={() => run(false)}>
          Import {good > 0 && good < (results?.length ?? 0) ? `${good} valid files` : ''}
        </button>
      </div>
      <fieldset className="field">
        <legend className="field-label">Templates for scripts</legend>
        <div className="row">
          <select aria-label="Template type" value={type} onChange={(e) => setType(e.target.value)}>
            {meta.component_types.map((t) => (
              <option key={t.code} value={t.code}>
                {t.name}
              </option>
            ))}
          </select>
          <a className="btn btn-small" href={`./api/product-templates/${type}/schema`} download>
            Schema
          </a>
          <a className="btn btn-small" href={`./api/product-templates/${type}/example`} download>
            Example
          </a>
        </div>
        <p className="small muted">
          Writing a script with an AI agent? Give it the <a href="./api/product-templates/instructions.md" download>instructions for script authors</a>; they cover every part type.
        </p>
      </fieldset>
    </div>
  )
}
