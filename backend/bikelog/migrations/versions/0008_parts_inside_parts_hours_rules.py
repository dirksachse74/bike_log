"""Ride-hours and "number of parents" reminders; wheelsets in the usage profiles

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25 23:30:00

* service_rule gets interval_hours / warn_hours (ride time, e.g. charge power-meter pedals every 50 h)
  and interval_count (trigger PARENT_COUNT: e.g. replace a quick link once it has been on 2 chains).
  The CHECK constraints change, so service_rule is rebuilt (it has no delete protection; its two
  requires_setup triggers are created again). Rows and ids are copied unchanged.
* Usage profiles that take both wheels out (trainer) also take out a wheelset.
New part types (wheelset, hub, bearings, spokes, rim tape, pulley wheels, power-meter pedals) need no
schema change; their default rules are added at startup.
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

SETUPS = "('TUBE','TUBELESS','TUBULAR')"
COLUMNS = ("id, uuid, rule_code, name, component_type, component_id, action_code, \"trigger\", interval_km, "
           "interval_months, window_min_km, window_max_km, cycle_action_code, reset_actions_json, warn_km, "
           "warn_days, origin, active, notes, created_at, updated_at, requires_setup")


def _create(table: str, *, new: bool) -> None:
    triggers = "'INTERVAL','CYCLE_WINDOW','PARENT_COUNT'" if new else "'INTERVAL','CYCLE_WINDOW'"
    interval = ("trigger <> 'INTERVAL' OR interval_km IS NOT NULL OR interval_months IS NOT NULL "
                "OR interval_hours IS NOT NULL") if new else \
        "trigger <> 'INTERVAL' OR interval_km IS NOT NULL OR interval_months IS NOT NULL"
    extra_cols = "interval_hours FLOAT, warn_hours FLOAT, interval_count INTEGER," if new else ""
    extra_checks = ("CONSTRAINT ck_rule_count CHECK (trigger <> 'PARENT_COUNT' OR interval_count >= 1),"
                    if new else "")
    op.execute(f"""
    CREATE TABLE {table} (
        id INTEGER NOT NULL, uuid VARCHAR(36) NOT NULL, rule_code VARCHAR(48) NOT NULL, name TEXT NOT NULL,
        component_type VARCHAR(32), component_id INTEGER, action_code VARCHAR(32) NOT NULL,
        "trigger" VARCHAR(16) NOT NULL, interval_km FLOAT, interval_months INTEGER, window_min_km FLOAT,
        window_max_km FLOAT, cycle_action_code VARCHAR(32), reset_actions_json TEXT NOT NULL, warn_km FLOAT,
        warn_days INTEGER, origin VARCHAR(16) NOT NULL, active BOOLEAN NOT NULL, notes TEXT,
        created_at VARCHAR(20) NOT NULL, updated_at VARCHAR(20) NOT NULL, requires_setup VARCHAR(12),
        {extra_cols}
        PRIMARY KEY (id),
        CONSTRAINT ck_rule_origin CHECK (origin IN ('DEFAULT','MANUFACTURER','PERSONAL')),
        CONSTRAINT ck_rule_window CHECK (trigger <> 'CYCLE_WINDOW' OR (window_min_km IS NOT NULL AND
            window_max_km >= window_min_km AND cycle_action_code IS NOT NULL)),
        CONSTRAINT ck_rule_interval CHECK ({interval}),
        CONSTRAINT ck_rule_trigger CHECK (trigger IN ({triggers})),
        {extra_checks}
        CONSTRAINT ck_rule_target CHECK ((component_type IS NULL) <> (component_id IS NULL)),
        FOREIGN KEY(component_id) REFERENCES component (id),
        UNIQUE (uuid)
    )""")


def _finish() -> None:
    op.execute("CREATE UNIQUE INDEX uq_rule_component_code ON service_rule (component_id, rule_code) "
               "WHERE component_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_rule_type_code ON service_rule (component_type, rule_code) "
               "WHERE component_type IS NOT NULL")
    for ev in ('INSERT', 'UPDATE'):
        op.execute(f"""
        CREATE TRIGGER trg_service_rule_requires_setup_{ev.lower()} BEFORE {ev} ON service_rule
        FOR EACH ROW WHEN NEW.requires_setup IS NOT NULL AND NEW.requires_setup NOT IN {SETUPS}
        BEGIN SELECT RAISE(ABORT, 'INVALID: service_rule.requires_setup must be TUBE, TUBELESS or TUBULAR'); END
        """)


def _rebuild(*, new: bool) -> None:
    for ev in ('insert', 'update'):
        op.execute(f"DROP TRIGGER IF EXISTS trg_service_rule_requires_setup_{ev}")
    _create("service_rule_new", new=new)
    if not new:   # downgrade: rules that only the new version understands cannot be kept
        op.execute("DELETE FROM service_rule WHERE trigger = 'PARENT_COUNT' OR (trigger = 'INTERVAL' AND "
                   "interval_km IS NULL AND interval_months IS NULL)")
    op.execute(f"INSERT INTO service_rule_new ({COLUMNS}) SELECT {COLUMNS} FROM service_rule")
    op.execute("DROP TABLE service_rule")
    op.execute("ALTER TABLE service_rule_new RENAME TO service_rule")
    _finish()


def _profiles(add: bool) -> None:
    conn = op.get_bind()
    for pid, slots_json in conn.execute(sa.text("SELECT id, excluded_slots_json FROM usage_profile")).all():
        slots = json.loads(slots_json or "[]")
        if add and "FRONT_WHEEL" in slots and "REAR_WHEEL" in slots and "WHEELSET" not in slots:
            slots.insert(0, "WHEELSET")
        elif not add and "WHEELSET" in slots:
            slots.remove("WHEELSET")
        else:
            continue
        conn.execute(sa.text("UPDATE usage_profile SET excluded_slots_json = :s WHERE id = :i"),
                     {"s": json.dumps(slots), "i": pid})


def upgrade() -> None:
    _rebuild(new=True)
    _profiles(add=True)


def downgrade() -> None:
    _profiles(add=False)
    _rebuild(new=False)
