// "Where does it go?": a position on a bike, or a part it mounts on (wheelset → front/rear wheel → hub →
// bearings; crankset → chainring; rear derailleur → pulleys), listed per bike and for parts off the bike.
// Taken positions are shown but cannot be picked. Optionally "Keep as a spare".
import { useApp } from '../context'
import { useApi } from '../hooks'
import { Field } from './ui'

export interface MountTarget {
  group: string
  bike_id: number | null
  parent_component_id: number | null
  slot: string | null
  text: string
  occupied_by: string | null
}

interface MountTargets {
  on_bike: boolean
  needs_parent: boolean
  targets: MountTarget[]
}

export default function MountPicker({ componentType, bikeId, value, onChange, allowSpare }: { componentType: string; bikeId?: number; value: MountTarget | null; onChange: (t: MountTarget | null) => void; allowSpare?: boolean }) {
  const { meta } = useApp()
  const q = useApi<MountTargets>(`/mount-targets?component_type=${componentType}${bikeId ? `&bike_id=${bikeId}` : ''}`)
  const ctype = meta.component_types.find((t) => t.code === componentType)
  const targets = q.data?.targets ?? []
  const groups = [...new Set(targets.map((t) => t.group))]
  const index = value ? targets.findIndex((t) => t.bike_id === value.bike_id && t.parent_component_id === value.parent_component_id && t.slot === value.slot) : -1
  const parents = (ctype?.parent_types ?? []).map((p) => meta.component_types.find((t) => t.code === p)?.name.toLowerCase() ?? p)
  const hint = q.data?.needs_parent
    ? `A ${ctype?.name.toLowerCase()} is mounted on a ${parents.join(' or ')}. Wheels inside a wheelset are listed with the wheelset.`
    : parents.length
      ? `On the bike, or mounted on a ${parents.join(' or ')}.`
      : undefined
  return (
    <Field label="Where does it go?" hint={hint}>
      <select
        aria-label="Where does it go?"
        value={index < 0 ? '' : String(index)}
        onChange={(e) => onChange(e.target.value === '' ? null : targets[Number(e.target.value)])}
      >
        {allowSpare ? <option value="">Keep as a spare (in storage)</option> : <option value="">Pick…</option>}
        {groups.map((g) => (
          <optgroup key={g} label={g}>
            {targets.map((t, i) =>
              t.group === g ? (
                <option key={i} value={i} disabled={!!t.occupied_by}>
                  {t.text}
                  {t.occupied_by ? ` (has ${t.occupied_by})` : ''}
                </option>
              ) : null,
            )}
          </optgroup>
        ))}
      </select>
      {q.data && targets.length === 0 && <span className="field-hint">Nothing to mount it on yet{parents.length ? `: add a ${parents.join(' or ')} first` : ''}.</span>}
    </Field>
  )
}
