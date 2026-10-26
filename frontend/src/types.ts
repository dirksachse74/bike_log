export type Status = 'OVERDUE' | 'DUE' | 'ATTENTION' | 'DUE_SOON' | 'INSUFFICIENT_INFO' | 'SNOOZED' | 'OK' | 'DONE_THIS_CYCLE' | 'DISABLED' | 'NOT_APPLICABLE'

export interface Usage {
  total_km: number
  ride_km: number
  uncertain_km?: number
  starting_km: number | null
  starting_is_estimate: boolean
  starting_effective: string | null
  ride_count: number
  rides_before_start?: number
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
  shifting: string | null
  shifting_effective: string | null
}

export interface BikeCosts {
  initial_cents: number | null
  initial_known: boolean
  purchase_date: string | null
  parts_cents: number
  stock_cents: number
  services_cents: number
  bundles_cents: number
  running_cents: number
  total_cents: number
  per_km_cents?: number | null
  estimated: boolean
  unpriced_parts: number
  unvalued_stock_uses: number
  unpriced_bundles: number
  items?: { kind: 'PART' | 'STOCK' | 'SERVICE' | 'BUNDLE'; date: string | null; text: string; cents: number; estimated: boolean; component_id?: number }[]
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
  bike?: string | null
  component_type?: string | null
  ride_id?: number | null
  ride_label?: string | null
  ride_conditions?: string | null
  incident_type?: string | null
  incident_label?: string | null
  incident_group?: string | null
  affected?: string | null
  via_child?: boolean
}

export interface IncidentChoice {
  key: string
  label: string
  component_id: number | null
  recorded: boolean
  wheel?: 'FRONT_WHEEL' | 'REAR_WHEEL'
  damage?: 'TUBE' | 'TIRE'
}

export interface SpareCheck {
  component_type: string
  type_name: string
  unit: string
  have: number
  minimum: number
  low: boolean
  text: string
}

export interface ShoppingItem {
  consumable_id: number | null
  component_type?: string
  name: string
  unit: string
  available: number
  min_stock: number
  suggested_qty: number
  text: string
}

export interface RideIncident {
  group: string
  incident_type: string
  label: string
  on: string
  text: string | null
  resolved_on: string | null
  open: boolean
  affected: { key: string; component_id: number | null; label: string; repair: 'REPLACED' | 'REPAIRED' | null; repair_text: string | null; repaired_on: string | null }[]
  removed: boolean
  edited: boolean
  fixable: boolean
  has_fix: boolean
  ride_id: number | null
  ride_label: string | null
  ride_conditions: 'DRY' | 'WET' | null
  bike_id: number | null
  bike: string | null
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
  mark?: string | null
  rotation_bike_id?: number | null
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
  tire_setup: TireSetup | null
  pressure_note: string | null
  warranty_until: string | null
  effective_tire_setup: TireSetup | null
  tire_setup_from: string | null
  location: Location
  usage: Usage
  bundle: BundleRef | null
}

export interface BundleRef {
  id: number
  name: string
  merchant: string | null
  purchased_on: string | null
  price_cents: number | null
  share_cents: number | null
}

export interface BundleMember {
  component_id: number
  label: string
  component_type: string
  type_name: string
  status: string
  state: Location['state']
  where: string
  in_use: boolean
  share_cents: number | null
}

export interface BundleRow {
  id: number
  name: string
  merchant: string | null
  purchased_on: string | null
  price_cents: number | null
  notes: string | null
  voided: boolean
  void_reason: string | null
  bike_id: number | null
  bike: string | null
  members: BundleMember[]
  in_use: number
  member_count: number
  share_basis: string
}

export interface BundleCandidate {
  component_id: number
  label: string
  component_type: string
  type_name: string
  where: string
  purchase_date: string | null
}

export interface Task {
  rule_code: string
  rule_id?: number
  name: string
  action_code: string
  component_id: number | null   // null: a bike-level reminder (torque check, frame inspection)
  component: string | null
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
  rotation?: { kind: 'SWAP' | 'WAX' | 'INSTALL'; text: string; to?: number; to_label?: string; bike_id: number }
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
  removed: boolean
  bike_overridden: boolean
  source_bike_id: number | null
  source_bike: string | null
  conditions: 'DRY' | 'WET' | null
  incidents: number
}

export interface RideDetail extends RideRow {
  equipment: { component_id: number; label: string; component_type: string; slot: string; km: number; hours: number | null; basis: string; certain: boolean; state: string; note: string | null }[]
  explicit_equipment: { slot: string; component_id: number | null; note: string | null }[]
  source_values: Record<string, unknown> | null
  counting_note: string | null
  summary: {
    km: number | null
    hours: number | null
    bike: {
      name: string
      total_km: number
      total_hours: number
      starting_km: number | null
      starting_is_estimate: boolean
      year: RidePeriod
      month: RidePeriod
    } | null
  }
}

export interface RidePeriod {
  label: string
  km: number
  hours: number
  rides: number
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
  mark: string | null
  wax_cycles: number
  rotation_bike_id: number | null
  wax_status?: Task | null
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
  unit?: string | null
  limits_source?: string | null
  limits?: { value: number; outcome: string; below: boolean }[]
  checklist?: string[]
}

export interface ComponentType {
  code: string
  name: string
  category: string
  slots: string[]
  parent_types: string[]
  removed_default: string
  rider_gear?: boolean
  torque?: boolean
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

export type TireSetup = 'TUBE' | 'TUBELESS' | 'TUBULAR'

export interface Meta {
  version: string
  schema: string
  commit: string
  ui_commit: string
  full_version: string
  release: boolean
  ui_version: string
  demo: boolean
  sample?: boolean
  safety_note: string
  settings: Record<string, string>
  component_types: ComponentType[]
  actions: ActionDef[]
  profiles: Profile[]
  dispositions: { code: string; label: string }[]
  tracking_modes: { code: string; label: string }[]
  tire_setups: { code: TireSetup; label: string }[]
  shifting_types: { code: string; label: string }[]
  incident_types: { code: string; label: string }[]
  ride_conditions: { code: string; label: string }[]
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
  trigger: 'INTERVAL' | 'CYCLE_WINDOW' | 'PARENT_COUNT' | 'ONCE_AFTER_INSTALL'
  interval_km: number | null
  interval_hours: number | null
  warn_hours: number | null
  interval_count: number | null
  notes: string | null
  interval_months: number | null
  window_min_km: number | null
  window_max_km: number | null
  cycle_action_code: string | null
  reset_actions: string[]
  warn_km: number | null
  warn_days: number | null
  origin: string
  active: boolean
  requires_setup: string | null   // a tire setup (TUBELESS) or a shifting type (MECHANICAL)
}

export interface ChangeRow {
  id: number
  changed_at: string
  action: string
  field: string | null
  old_value: string | null
  new_value: string | null
  source: string
  who: string
  via: string | null
  component_id: number | null
  component: string | null
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
  parent_component_id: number | null
  tire_setup: TireSetup | null
  spokes?: SpokeInfo
  pressure_note: string | null
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
  kept_as_spare?: boolean
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

export interface FixSourceOptions {
  replace: boolean
  stock: { id: number; name: string; unit: string; qty: number }[]
  spares: { id: number; label: string }[]
  suggested_outcome?: string
  outcomes?: { code: string; label: string }[]
  wheel_label?: string | null
  installed_component_id?: number | null
  tracks_new?: boolean
}

export interface FixPartOption {
  entry_id: number
  label: string
  component_id: number | null
  kind: 'PART' | 'POSITION' | 'OTHER' | 'SPOKE'
  damage: 'TUBE' | 'TIRE' | null
  repair: string | null
  repair_text: string | null
  repair_label?: string
  options: FixSourceOptions | null
}

export interface FixOptions {
  group: string
  label: string
  ride_date: string
  bike_id: number | null
  parts: FixPartOption[]
}

export interface SpokeInfo {
  wheel_id: number
  component_id: number | null
  label: string | null
  product?: string | null
  specs: { count?: number; model?: string; length_mm?: number; length_drive_mm?: number; length_non_drive_mm?: number; nipples?: string }
  from_product: string[]
  broken: number
  since: string | null
  relace_after: number
}

// A part with the parts mounted on it now (wheelset → wheels → hub, tire ...), for drilling down.
export interface PartNode {
  component_id: number
  label: string
  component_type: string
  type_name: string
  slot: string
  since: string
  usage: Usage
  due: number
  depth: number
  on?: string | null
  children: PartNode[]
}

export interface GroupsetSummary {
  name: string
  parts: number
  due: number
  top: string[]
  since: string
}

export interface GroupsetPageData {
  bike_id: number
  bike: string
  name: string | null
  since: string | null
  stats: { km: number; hours: number; rides_without_time: number; parts: number; due: number }
  parts: PartNode[]
  events: EventRow[]
  journal: JournalRow[]
  incidents: RideIncident[]
  tasks: Task[]
}

export interface ChainRotationData {
  bike_id: number
  bike: string
  chains: ChainRow[]
  on: number | null
  next_ready: number | null
  dirty: number[]
  prompt: { kind: 'SWAP' | 'WAX' | 'INSTALL'; text: string; to?: number; to_label?: string } | null
  candidates: { component_id: number; label: string; mark: string | null }[]
  timeline: { kind: 'ON' | 'WAX'; date: string; until: string | null; component_id: number; label: string; km: number | null }[]
}
