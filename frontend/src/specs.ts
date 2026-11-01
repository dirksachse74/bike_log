// Part properties: form strings ↔ stored values (components/Properties.tsx).
import type { SpecFieldDef } from './types'

export type Raw = Record<string, string>

export const show = (v: unknown) => (typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v))

export function toRaw(fields: SpecFieldDef[], specs: Record<string, unknown>): Raw {
  return Object.fromEntries(fields.filter((f) => specs[f.key] !== undefined && specs[f.key] !== null).map((f) => [f.key, show(specs[f.key])]))
}

// The values entered, as stored (numbers as numbers, yes/no as true/false); throws on a bad number.
export function specsFrom(fields: SpecFieldDef[], raw: Raw): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    const v = (raw[f.key] ?? '').trim()
    if (!v) continue
    if (f.kind === 'number' || f.kind === 'integer') {
      const n = Number(v.replace(',', '.'))
      if (Number.isNaN(n)) throw new Error(`${f.label}: enter a number, e.g. ${f.unit === '°' ? '-10' : '100'}`)
      out[f.key] = f.kind === 'integer' ? Math.round(n) : n
    } else if (f.kind === 'boolean') out[f.key] = v === 'yes'
    else out[f.key] = v
  }
  return out
}

