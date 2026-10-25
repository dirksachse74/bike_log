import type { Status, Usage } from './types'

let tz = 'Europe/Berlin'
export function setTimezone(z: string) {
  tz = z || tz
}

export function km(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return 'unknown'
  return `${v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })} km`
}

/** Date-only values stay date-only; instants are shown in the user's timezone. */
export function when(value: string | null | undefined): string {
  if (!value) return '—'
  if (value.length === 10) return new Date(value + 'T12:00:00Z').toLocaleDateString(undefined, { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' })
  const d = new Date(value)
  return d.toLocaleString(undefined, { timeZone: tz, year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function duration(s: number | null | undefined): string {
  if (!s) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h ? `${h} h ${m.toString().padStart(2, '0')} min` : `${m} min`
}

export function today(): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  return parts
}

export const STATUS_LABEL: Record<Status, string> = {
  OVERDUE: 'Overdue',
  DUE: 'Due',
  ATTENTION: 'Attention',
  DUE_SOON: 'Due soon',
  INSUFFICIENT_INFO: 'Not enough info',
  SNOOZED: 'Snoozed',
  OK: 'OK',
  DONE_THIS_CYCLE: 'Done this cycle',
  DISABLED: 'Off',
}

export function usageText(u: Usage): string {
  const total = km(u.total_km, 0)
  if (u.certainty === 'ESTIMATED') return `≈ ${total}`
  if (u.is_minimum || u.certainty === 'INCOMPLETE') return `≥ ${total}`
  return total
}

export function certaintyLabel(u: Usage): string {
  switch (u.certainty) {
    case 'ESTIMATED':
      return 'includes an estimated starting value'
    case 'INCOMPLETE':
      return 'earlier usage unknown: this is a minimum'
    case 'PARTLY_UNCERTAIN':
      return 'some rides are uncertain or missing distance'
    default:
      return 'known'
  }
}

export const slotName = (s: string | null | undefined) => (s ? s.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : '')

/** Euro amount from cents; empty for unknown. */
export function euro(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return ''
  return (cents / 100).toLocaleString(undefined, { style: 'currency', currency: 'EUR' })
}

/** "12,50" or "12.50" → 1250; empty → null. */
export function toCents(value: string): number | null {
  const v = value.trim().replace(/\s/g, '').replace(',', '.')
  if (!v) return null
  const n = Number(v)
  return Number.isFinite(n) ? Math.round(n * 100) : NaN
}

export function centsInput(cents: number | null | undefined): string {
  return cents === null || cents === undefined ? '' : (cents / 100).toFixed(2)
}
