"""SQLAlchemy models: the authoritative schema. Alembic migrations in migrations/versions mirror it
(tests/test_migrations.py checks that models and migrations do not drift).

Conventions
* Every user-visible record has a stable ``uuid`` for exports and restores.
* Instants are UTC text ``YYYY-MM-DDTHH:MM:SSZ``; date-only inputs keep their date (see timeutil).
* Nothing with history is hard-deleted: records are voided, retired or excluded instead.
* ``usage_contribution`` is the only source of component usage. It is rebuildable from rides,
  installations, explicit ride equipment, usage profiles and starting values.
"""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bikelog.timeutil import utc_now


def new_uuid() -> str:
    return str(_uuid.uuid4())


class Base(DeclarativeBase):
    pass


class AppSetting(Base):
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Product(Base):
    """A product model (what you can buy): specs with their source. Not a physical part."""
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    component_type: Mapped[str] = mapped_column(String(32))
    maker: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    specs_json: Mapped[str] = mapped_column(Text, default="{}")
    spec_source: Mapped[str | None] = mapped_column(Text)     # e.g. URL or "manual"
    spec_version: Mapped[str | None] = mapped_column(Text)    # e.g. "2026 datasheet"
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class Bike(Base):
    __tablename__ = "bike"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_bike_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    name: Mapped[str] = mapped_column(Text, unique=True)
    maker: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    strava_gear_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(20), default=utc_now, onupdate=utc_now)


class Component(Base):
    """One physical part you own. Identity never changes, whatever bike it is on."""
    __tablename__ = "component"
    __table_args__ = (
        UniqueConstraint("component_type", "label", name="uq_component_type_label"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_component_status"),
        CheckConstraint("prior_usage IN ('NEW','RECORDED','UNKNOWN')", name="ck_component_prior_usage"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    component_type: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(Text)                    # "Chain A"
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"))
    serial_number: Mapped[str | None] = mapped_column(Text)     # private by default
    # NEW: 0 km when tracking started. RECORDED: see usage_adjustment STARTING. UNKNOWN: prior use unknown.
    prior_usage: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    purchase_date: Mapped[str | None] = mapped_column(String(10))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    retired_on: Mapped[str | None] = mapped_column(String(10))
    retire_reason: Mapped[str | None] = mapped_column(Text)
    specs_json: Mapped[str] = mapped_column(Text, default="{}")  # instance-specific specs (override product)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(20), default=utc_now, onupdate=utc_now)

    product: Mapped[Product | None] = relationship()


class Installation(Base):
    """Fitment history. Start-inclusive, end-exclusive. Mounted on a bike or on another component."""
    __tablename__ = "installation"
    __table_args__ = (
        CheckConstraint("(bike_id IS NULL) <> (parent_component_id IS NULL)", name="ck_installation_target"),
        CheckConstraint("removed_utc IS NULL OR removed_utc > installed_utc", name="ck_installation_order"),
        Index("uq_installation_open_component", "component_id", unique=True,
              sqlite_where=text("removed_utc IS NULL AND voided_at IS NULL")),
        Index("uq_installation_open_bike_slot", "bike_id", "slot", unique=True,
              sqlite_where=text("removed_utc IS NULL AND voided_at IS NULL AND bike_id IS NOT NULL")),
        Index("uq_installation_open_parent_slot", "parent_component_id", "slot", unique=True,
              sqlite_where=text("removed_utc IS NULL AND voided_at IS NULL AND parent_component_id IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id"), index=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bike.id"), index=True)
    parent_component_id: Mapped[int | None] = mapped_column(ForeignKey("component.id"), index=True)
    slot: Mapped[str] = mapped_column(String(32))
    installed_at: Mapped[str] = mapped_column(String(20))      # as entered (date or UTC datetime)
    installed_utc: Mapped[str] = mapped_column(String(20))     # ordering instant
    removed_at: Mapped[str | None] = mapped_column(String(20))
    removed_utc: Mapped[str | None] = mapped_column(String(20))
    removal_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[str | None] = mapped_column(String(20))  # correction: record was wrong
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)

    component: Mapped[Component] = relationship(foreign_keys=[component_id])


class UsageAdjustment(Base):
    """Starting mileage (with effective date and estimate flag) or an explicit correction."""
    __tablename__ = "usage_adjustment"
    __table_args__ = (
        CheckConstraint("(bike_id IS NULL) <> (component_id IS NULL)", name="ck_adjustment_target"),
        CheckConstraint("kind IN ('STARTING','CORRECTION')", name="ck_adjustment_kind"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("component.id"), index=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bike.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    effective_at: Mapped[str] = mapped_column(String(20))
    effective_utc: Mapped[str] = mapped_column(String(20))
    km: Mapped[float] = mapped_column(Float)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class UsageProfile(Base):
    """How a ride uses the bike. A trainer profile lists equipment that is removed or not worn."""
    __tablename__ = "usage_profile"
    __table_args__ = (CheckConstraint("kind IN ('OUTDOOR','TRAINER')", name="ck_profile_kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    excluded_slots_json: Mapped[str] = mapped_column(Text, default="[]")
    excluded_types_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text)


class Ride(Base):
    """Effective ride values (source values with local overrides applied)."""
    __tablename__ = "ride"
    __table_args__ = (
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_ride_distance"),
        CheckConstraint("status IN ('ACTIVE','SOURCE_DELETED')", name="ck_ride_status"),
        CheckConstraint("inclusion IN ('INCLUDED','EXCLUDED')", name="ck_ride_inclusion"),
        CheckConstraint("source_kind IN ('MANUAL','CSV','STRAVA')", name="ck_ride_source_kind"),
        Index("ix_ride_bike_sort", "bike_id", "sort_utc"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bike.id"))
    name: Mapped[str | None] = mapped_column(Text)
    ride_date: Mapped[str] = mapped_column(String(10))           # local date
    start_time_utc: Mapped[str | None] = mapped_column(String(20))  # NULL = date-only ride
    sort_utc: Mapped[str] = mapped_column(String(20))
    distance_km: Mapped[float | None] = mapped_column(Float)     # NULL = missing, not zero
    duration_s: Mapped[int | None] = mapped_column(Integer)
    sport_type: Mapped[str] = mapped_column(String(32), default="Ride")
    usage_profile_id: Mapped[int | None] = mapped_column(ForeignKey("usage_profile.id"))
    source_kind: Mapped[str] = mapped_column(String(16), default="MANUAL")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    inclusion: Mapped[str] = mapped_column(String(16), default="INCLUDED")
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    assignment_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    uncertainty_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(20), default=utc_now, onupdate=utc_now)


class RideSource(Base):
    """Identity and values of an imported ride. One source record is forever one ride."""
    __tablename__ = "ride_source"
    __table_args__ = (UniqueConstraint("source_kind", "source_account", "source_ref", name="uq_ride_source_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id"), unique=True)
    source_kind: Mapped[str] = mapped_column(String(16))       # CSV, STRAVA
    source_account: Mapped[str] = mapped_column(String(64))    # e.g. CSV profile name or athlete id
    source_ref: Mapped[str] = mapped_column(String(128))       # id within the source
    values_json: Mapped[str] = mapped_column(Text)             # what the source said
    payload_hash: Mapped[str] = mapped_column(String(64))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    first_seen_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    last_seen_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class RideOverride(Base):
    """A local correction of one field. Imports never touch these."""
    __tablename__ = "ride_override"
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id"), primary_key=True)
    field: Mapped[str] = mapped_column(String(32), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    set_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class RideEquipment(Base):
    """Explicit equipment for a ride slot; overrides installation history. component_id NULL = none used."""
    __tablename__ = "ride_equipment"
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id"), primary_key=True)
    slot: Mapped[str] = mapped_column(String(32), primary_key=True)
    component_id: Mapped[int | None] = mapped_column(ForeignKey("component.id"))
    note: Mapped[str | None] = mapped_column(Text)


class UsageContribution(Base):
    """Materialised allocation of a ride to a component. Rebuilt per ride, never appended."""
    __tablename__ = "usage_contribution"
    __table_args__ = (
        CheckConstraint("state IN ('COUNTED','IN_BASELINE')", name="ck_contribution_state"),
        CheckConstraint("basis IN ('HISTORY','EXPLICIT')", name="ck_contribution_basis"),
        Index("ix_contribution_component", "component_id", "sort_utc"),
    )
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id"), primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id"), primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bike.id"))
    slot: Mapped[str] = mapped_column(String(32))
    sort_utc: Mapped[str] = mapped_column(String(20))
    km: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(String(16))
    certain: Mapped[bool] = mapped_column(Boolean)
    state: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)


class RideFlag(Base):
    """Review flags computed by the allocator (rebuilt with the ride's contributions)."""
    __tablename__ = "ride_flag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    slot: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text)


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_event"
    __table_args__ = (Index("ix_event_component_action", "component_id", "action_code", "sort_utc"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    action_code: Mapped[str] = mapped_column(String(32))
    component_id: Mapped[int | None] = mapped_column(ForeignKey("component.id"))
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bike.id"))
    performed_at: Mapped[str] = mapped_column(String(20))   # as entered
    performed_on: Mapped[str] = mapped_column(String(10))   # local date
    sort_utc: Mapped[str] = mapped_column(String(20))
    symptom: Mapped[str | None] = mapped_column(Text)
    work_done: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    measurement_value: Mapped[float | None] = mapped_column(Float)
    measurement_unit: Mapped[str | None] = mapped_column(String(16))
    consumable_id: Mapped[int | None] = mapped_column(ForeignKey("consumable.id"))
    consumable_qty: Mapped[float | None] = mapped_column(Float)
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    batch_ref: Mapped[str | None] = mapped_column(String(36))  # events logged together
    voided_at: Mapped[str | None] = mapped_column(String(20))
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class ServiceRule(Base):
    """Type-level default or component-level rule. A component rule with the same rule_code replaces
    the type rule for that component (active=False disables it)."""
    __tablename__ = "service_rule"
    __table_args__ = (
        CheckConstraint("(component_type IS NULL) <> (component_id IS NULL)", name="ck_rule_target"),
        CheckConstraint("trigger IN ('INTERVAL','CYCLE_WINDOW')", name="ck_rule_trigger"),
        CheckConstraint("origin IN ('DEFAULT','MANUFACTURER','PERSONAL')", name="ck_rule_origin"),
        CheckConstraint("trigger <> 'INTERVAL' OR interval_km IS NOT NULL OR interval_months IS NOT NULL",
                        name="ck_rule_interval"),
        CheckConstraint("trigger <> 'CYCLE_WINDOW' OR (window_min_km IS NOT NULL AND window_max_km >= window_min_km "
                        "AND cycle_action_code IS NOT NULL)", name="ck_rule_window"),
        Index("uq_rule_type_code", "component_type", "rule_code", unique=True,
              sqlite_where=text("component_type IS NOT NULL")),
        Index("uq_rule_component_code", "component_id", "rule_code", unique=True,
              sqlite_where=text("component_id IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    rule_code: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(String(32))
    component_id: Mapped[int | None] = mapped_column(ForeignKey("component.id"))
    action_code: Mapped[str] = mapped_column(String(32))
    trigger: Mapped[str] = mapped_column(String(16), default="INTERVAL")
    interval_km: Mapped[float | None] = mapped_column(Float)
    interval_months: Mapped[int | None] = mapped_column(Integer)
    window_min_km: Mapped[float | None] = mapped_column(Float)
    window_max_km: Mapped[float | None] = mapped_column(Float)
    cycle_action_code: Mapped[str | None] = mapped_column(String(32))
    reset_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    warn_km: Mapped[float | None] = mapped_column(Float)
    warn_days: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16), default="PERSONAL")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(20), default=utc_now, onupdate=utc_now)


class ReminderSnooze(Base):
    """Hide a reminder until a date and/or extra km. Records no maintenance."""
    __tablename__ = "reminder_snooze"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(48))
    until_date: Mapped[str | None] = mapped_column(String(10))
    until_km: Mapped[float | None] = mapped_column(Float)  # usage-since-reset at which it shows again
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    cleared_at: Mapped[str | None] = mapped_column(String(20))


class Consumable(Base):
    """Wax, lube, sealant, brake fluid... tracked by product with optional stock."""
    __tablename__ = "consumable"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(24))       # WAX, LUBE, SEALANT, BRAKE_FLUID, GREASE, OTHER
    name: Mapped[str] = mapped_column(Text, unique=True)
    maker: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(16), default="ml")
    track_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class ConsumableTxn(Base):
    """Buying, using and adjusting stock are separate events."""
    __tablename__ = "consumable_txn"
    __table_args__ = (CheckConstraint("kind IN ('PURCHASE','USE','ADJUST')", name="ck_consumable_txn_kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumable_id: Mapped[int] = mapped_column(ForeignKey("consumable.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float | None] = mapped_column(Float)    # USE may be unknown
    occurred_on: Mapped[str] = mapped_column(String(10))
    maintenance_event_id: Mapped[int | None] = mapped_column(ForeignKey("maintenance_event.id"))
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class ImportBatch(Base):
    """One import run. Resumable: cursor_row is committed together with the rows it covers."""
    __tablename__ = "import_batch"
    __table_args__ = (CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')", name="ck_import_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    source_kind: Mapped[str] = mapped_column(String(16))
    source_account: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    rows_total: Mapped[int | None] = mapped_column(Integer)
    cursor_row: Mapped[int] = mapped_column(Integer, default=0)
    counts_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str] = mapped_column(String(20), default=utc_now)
    finished_at: Mapped[str | None] = mapped_column(String(20))


class Operation(Base):
    """Idempotency log: a repeated client_op_id returns the stored result instead of re-running."""
    __tablename__ = "operation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_op_id: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(48))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(20), default=utc_now)


class StravaConnection(Base):
    """Isolated Strava connector state. No secrets here: tokens live in a file in the data dir."""
    __tablename__ = "strava_connection"
    __table_args__ = (
        CheckConstraint("status IN ('NOT_CONNECTED','ACTIVE','PAUSED','DISCONNECTED')", name="ck_strava_status"),
        CheckConstraint("retention_mode IN ('PERMANENT','PROVISIONAL')", name="ck_strava_retention"),
    )
    athlete_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="NOT_CONNECTED")
    retention_mode: Mapped[str] = mapped_column(String(16), default="PROVISIONAL")
    cursor_epoch: Mapped[int | None] = mapped_column(Integer)
    last_success_at: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(20), default=utc_now, onupdate=utc_now)
