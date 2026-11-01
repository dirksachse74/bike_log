import { useState } from 'react'
import { useApi } from '../hooks'
import { Field } from './ui'

const NEW = '__new__'

// "Bought from": pick a shop you used before, or type a new one (it joins the list when saved).
// The list is managed in Settings → Lists (DECISIONS 106).
export default function ShopPicker({ value, onChange, label = 'Bought from (optional)', list = 'SHOP' }: { value: string; onChange: (v: string) => void; label?: string; list?: string }) {
  const names = useApi<string[]>(`/lists/${list}`)
  const known = names.data ?? []
  const [typing, setTyping] = useState(false)
  const options = value && !known.some((n) => n.toLowerCase() === value.toLowerCase()) && !typing ? [value, ...known] : known
  return (
    <>
      <Field label={label}>
        <select
          aria-label={label}
          value={typing ? NEW : options.find((n) => n.toLowerCase() === value.toLowerCase()) ?? ''}
          onChange={(e) => {
            if (e.target.value === NEW) {
              setTyping(true)
              onChange('')
            } else {
              setTyping(false)
              onChange(e.target.value)
            }
          }}
        >
          <option value="">— not entered —</option>
          {options.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
          <option value={NEW}>New shop…</option>
        </select>
      </Field>
      {typing && (
        <Field label="New shop name" hint="It is added to your shop list when you save.">
          <input autoFocus value={value} onChange={(e) => onChange(e.target.value)} placeholder="e.g. bike-components.de" />
        </Field>
      )}
    </>
  )
}
