import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import type { TireSetup } from '../types'

// Tube or tubeless is set on the wheel, so it moves with the wheel (wheelset) to another bike.
// The tire and tube on the wheel follow it; the sealant reminder only runs for tubeless.
export function TireSetupSelect({ wheelId, value, onSaved }: { wheelId: number; value: TireSetup | null; onSaved: () => void }) {
  const { meta, toast } = useApp()
  const [busy, setBusy] = useState(false)
  async function save(v: string) {
    setBusy(true)
    try {
      await api.patch(`/components/${wheelId}`, { tire_setup: v || null })
      onSaved()
    } catch (e) {
      toast((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <select aria-label="Tire setup" className="select-small" disabled={busy} value={value ?? ''} onChange={(e) => save(e.target.value)} onClick={(e) => e.stopPropagation()}>
      <option value="">tube or tubeless?</option>
      {meta.tire_setups.map((s) => (
        <option key={s.code} value={s.code}>
          {s.label}
        </option>
      ))}
    </select>
  )
}
