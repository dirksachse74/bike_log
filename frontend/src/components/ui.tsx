import { type ReactNode, useEffect } from 'react'
import { STATUS_LABEL } from '../format'
import type { Change, Status } from '../types'

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge st-${status.toLowerCase()}`}>{STATUS_LABEL[status] ?? status}</span>
}

export function Tag({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'warn' | 'info' | 'bad' | 'good'; title?: string }) {
  return (
    <span className={`tag tag-${tone}`} title={title}>
      {children}
    </span>
  )
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden /> {what}…
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>Something went wrong.</strong> {error}
      {onRetry && (
        <button className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children && <div>{children}</div>}
    </div>
  )
}

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h2>{title}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  )
}

export function FormError({ error, form = true }: { error: string | null; form?: boolean }) {
  if (!error) return null
  return (
    <div className="form-error" role="alert">
      {error} {form && <span className="muted">Your entries are kept; fix and save again.</span>}
    </div>
  )
}

export function ChangeNotice({ change }: { change: Change | null | undefined }) {
  if (!change) return null
  return <div className={`notice ${change.preview ? 'notice-preview' : ''}`}>{change.notice}</div>
}
