export type Status = 'OVERDUE' | 'DUE' | 'ATTENTION' | 'DUE_SOON' | 'INSUFFICIENT_INFO' | 'SNOOZED' | 'OK' | 'DONE_THIS_CYCLE' | 'DISABLED'

export interface Usage {
  total_km: number
  ride_km: number
  uncertain_km?: number
  starting_km: number | null
  starting_is_estimate: boolean
  starting_effective: string | null
  ride_count: number
  hours: number
  certainty: 'KNOWN' | 'ESTIMATED' | 'INCOMPLETE' | 'PARTLY_UNCERTAIN'
  is_minimum?: boolean
  summary?: string
  missing_distance_rides?: number
}

export interface Bike {
  id: number
  name: string
  maker: string | null
  model: string | null
  year: number | null
  status: string
  strava_gear_id: string | null
  notes: string | null
  usage: Usage
  open_tasks: number
  purchase_price_cents: number | null
  purchase_date: string | null
  costs: BikeCosts
}

export interface BikeCosts {
  initial_cents: number | null
  initial_known: boolean
  purchase_date: string | null
  parts_cents: number
  stock_cents: number
  services_cents: number
  running_cents: number
  total_cents: number
  per_km_cents?: number | null
  estimated: boolean
  unpriced_parts: number
  unvalued_stock_uses: number
  items?: { kind: 'PART' | 'STOCK' | 'SERVICE'; date: string | null; text: string; cents: number; estimated: boolean; component_id?: number }[]
  unpriced_labels?: string[]
}

export interface JournalRow {
  id: number
  source: 'JOURNAL' | 'MAINTENANCE'
  on: string
  kind: 'NOTE' | 'ISSUE' | 'MAINTENANCE'
  text: string
  resolved_on: string | null
  open_issue: boolean
  bike_id: number | null
  component_id: number | null
  component_label: string | null
  edited: boolean
  voided: boolean
}

export interface Location {
  state: 'INSTALLED' | 'STORED' | 'AWAITING_SERVICE' | 'RETIRED'
  disposition?: string
  text: string
  bike_id?: number | null
  bike?: string | null
  slot?: string
  since?: string
  installation_id?: number
  parent_component_id?: number | null
}

export interface ComponentSummary {
  id: number
  label: string
  component_type: string
  type_name: string
  category: string | null
  product: string | null
  product_id: number | null
  prior_usage: string
  status: string
  purchase_date: string | null
  price_cents: number | null
  notes: string | null
  serial_number: string | null
  disposition: string
  storage_location: string | null
  location: Location
  usage: Usage
}

export interface Task {
  rule_code: string
  rule_id?: number
  name: string
  action_code: string
  component_id: number
  component: string
  component_type: string
  status: Status
  underlying_status?: Status
  explanation: string
  bike?: string | null
  bike_id?: number | null
  used_km?: number | null
  due_date?: string
  snooze_id?: number
  origin?: string
}

export interface Flag {
  code: string
  slot: string | null
  detail: string
}

export interface RideRow {
  id: number
  name: string | null
  ride_date: string
  start_time_utc: string | null
  date_only: boolean
  distance_km: number | null
  duration_s: number | null
  sport_type: string
  bike_id: number | null
  bike: string | null
  usage_profile: string | null
  usage_profile_name: string | null
  source_kind: string
  status: string
  inclusion: 'INCLUDED' | 'EXCLUDED'
  exclusion_reason: string | null
  assignment_uncertain: boolean
  uncertainty_note: string | null
  notes: string | null
  flags: Flag[]
  overridden_fields: string[]
}

export interface RideDetail extends RideRow {
  equipment: { component_id: number; label: string; component_type: string; slot: string; km: number; basis: string; certain: boolean; state: string; note: string | null }[]
  explicit_equipment: { slot: string; component_id: number | null; note: string | null }[]
  source_values: Record<string, unknown> | null
}

export interface Change {
  preview: boolean
  deltas: { component_id: number; label: string; before_km: number; after_km: number; delta_km: number }[]
  notice: string
}

export interface OpResult<T> {
  result: T
  change: Change
  repeated?: boolean
}

export interface ChainRow {
  component_id: number
  label: string
  state: string
  text: string
  lifetime_km: number
  km_since_hot_wax: number | null
  last_hot_wax: string | null
  last_wear: { date: string; value: number | null; unit: string | null; outcome: string | null } | null
  location: Location
}

export interface BrakeRow {
  component_id: number
  label: string
  position: string | null
  location: Location
  fluid: Task | null
  last_bleed: { date: string; symptom: string | null; work_done: string | null; outcome: string | null } | null
}

export interface ActionDef {
  code: string
  name: string
  kind: string
  targets: string[]
  quick: boolean
  fields: string[]
  outcomes: string[]
}

export interface ComponentType {
  code: string
  name: string
  category: string
  slots: string[]
  parent_types: string[]
  removed_default: string
}

export interface Profile {
  id: number
  code: string
  name: string
  kind: string
  excluded_slots: string[]
  excluded_types: string[]
  notes: string | null
}

export interface Meta {
  version: string
  demo: boolean
  safety_note: string
  settings: Record<string, string>
  component_types: ComponentType[]
  actions: ActionDef[]
  profiles: Profile[]
  dispositions: { code: string; label: string }[]
  tracking_modes: { code: string; label: string }[]
}

export interface EventRow {
  id: number
  action_code: string
  action: string
  component_id: number | null
  component: string | null
  bike: string | null
  performed_at: string
  performed_on: string
  date_only: boolean
  symptom: string | null
  work_done: string | null
  outcome: string | null
  measurement_value: number | null
  measurement_unit: string | null
  consumable: string | null
  notes: string | null
  voided: boolean
  void_reason: string | null
}

export interface Rule {
  id: number
  rule_code: string
  name: string
  component_type: string | null
  component_id: number | null
  action_code: string
  action: string
  trigger: 'INTERVAL' | 'CYCLE_WINDOW'
  interval_km: number | null
  interval_months: number | null
  window_min_km: number | null
  window_max_km: number | null
  cycle_action_code: string | null
  reset_actions: string[]
  warn_km: number | null
  warn_days: number | null
  origin: string
  active: boolean
}

export interface SetupRow {
  component_id: number
  label: string
  component_type: string
  type_name: string
  slot: string
  since: string
  installation_id: number
  depth: number
}

export interface GroupsetTemplate {
  code: string
  name: string
  maker: string
  series: string
  speeds: number
  notes: string | null
  source: string
  checked_on: string | null
  verified: boolean
  label_prefix: string
  options: { key: string; label: string; default: string; choices: { value: string; label: string }[] }[]
  items: { key: string; type: string; type_name: string; name: string; default: boolean; when: Record<string, string[]> | null }[]
  occupied_modes: { code: string; label: string }[]
}

export interface GroupsetPlanItem {
  key: string
  type: string
  type_name: string
  model: string
  label: string
  action: 'INSTALL' | 'REPLACE' | 'SPARE'
  list_price_cents: number | null
  text: string
  product_exists: boolean
  replaces_label?: string
}

export interface GroupsetPlan {
  template: string
  name: string
  verified: boolean
  bike_id: number | null
  bike_name: string | null
  items: GroupsetPlanItem[]
  counts: { INSTALL: number; REPLACE: number; SPARE: number }
  new_products: number
}
