"""Bike-level reminders, once-after-install reminders, shifting type per bike

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26 00:30:00

* service_rule gets bike_id (a rule for one bike) and accepts component_type "BIKE" (bike-level type
  default, e.g. torque check every 3 months) and the trigger ONCE_AFTER_INSTALL (e.g. bed in new pads).
  The CHECK constraints change, so service_rule is rebuilt again (same way as 0008); requires_setup also
  accepts ELECTRONIC / MECHANICAL (the bike's shifting).
* reminder_snooze gets bike_id and component_id becomes optional (snoozing a bike-level reminder).
* bike.shifting: ELECTRONIC / MECHANICAL / NULL.
* Disposition IN_USE (shoes worn by the rider): the two disposition triggers accept it.
* Default rules that changed are updated only where they were never edited (origin DEFAULT):
  rim-tape check for every tire setup, tire check also yearly, lever coin cells 18 months.
New part types (shoes, cleats, stem, hanger, cables, valves, computer, lights, radar) need no schema
change; their default rules are added at startup.
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

OLD_SETUPS = "('TUBE','TUBELESS','TUBULAR')"
NEW_SETUPS = "('TUBE','TUBELESS','TUBULAR','ELECTRONIC','MECHANICAL')"
COLUMNS = ("id, uuid, rule_code, name, component_type, component_id, action_code, \"trigger\", interval_km, "
           "interval_months, window_min_km, window_max_km, cycle_action_code, reset_actions_json, warn_km, "
           "warn_days, origin, active, notes, created_at, updated_at, requires_setup, interval_hours, warn_hours, "
           "interval_count")


def _create(table: str, *, new: bool) -> None:
    triggers = ("'INTERVAL','CYCLE_WINDOW','PARENT_COUNT','ONCE_AFTER_INSTALL'" if new
                else "'INTERVAL','CYCLE_WINDOW','PARENT_COUNT'")
    target = ("(component_type IS NOT NULL) + (component_id IS NOT NULL) + (bike_id IS NOT NULL) = 1" if new
              else "(component_type IS NULL) <> (component_id IS NULL)")
    bike_col = "bike_id INTEGER," if new else ""
    bike_fk = "FOREIGN KEY(bike_id) REFERENCES bike (id)," if new else ""
    op.execute(f"""
    CREATE TABLE {table} (
        id INTEGER NOT NULL, uuid VARCHAR(36) NOT NULL, rule_code VARCHAR(48) NOT NULL, name TEXT NOT NULL,
        component_type VARCHAR(32), component_id INTEGER, {bike_col} action_code VARCHAR(32) NOT NULL,
        "trigger" VARCHAR({20 if new else 16}) NOT NULL, interval_km FLOAT, interval_months INTEGER,
        window_min_km FLOAT, window_max_km FLOAT, cycle_action_code VARCHAR(32), reset_actions_json TEXT NOT NULL,
        warn_km FLOAT, warn_days INTEGER, origin VARCHAR(16) NOT NULL, active BOOLEAN NOT NULL, notes TEXT,
        created_at VARCHAR(20) NOT NULL, updated_at VARCHAR(20) NOT NULL, requires_setup VARCHAR(12),
        interval_hours FLOAT, warn_hours FLOAT, interval_count INTEGER,
        PRIMARY KEY (id),
        CONSTRAINT ck_rule_origin CHECK (origin IN ('DEFAULT','MANUFACTURER','PERSONAL')),
        CONSTRAINT ck_rule_window CHECK (trigger <> 'CYCLE_WINDOW' OR (window_min_km IS NOT NULL AND
            window_max_km >= window_min_km AND cycle_action_code IS NOT NULL)),
        CONSTRAINT ck_rule_interval CHECK (trigger <> 'INTERVAL' OR interval_km IS NOT NULL OR
            interval_months IS NOT NULL OR interval_hours IS NOT NULL),
        CONSTRAINT ck_rule_trigger CHECK (trigger IN ({triggers})),
        CONSTRAINT ck_rule_count CHECK (trigger <> 'PARENT_COUNT' OR interval_count >= 1),
        CONSTRAINT ck_rule_target CHECK ({target}),
        FOREIGN KEY(component_id) REFERENCES component (id),
        {bike_fk}
        UNIQUE (uuid)
    )""")


def _finish(*, new: bool) -> None:
    op.execute("CREATE UNIQUE INDEX uq_rule_component_code ON service_rule (component_id, rule_code) "
               "WHERE component_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_rule_type_code ON service_rule (component_type, rule_code) "
               "WHERE component_type IS NOT NULL")
    if new:
        op.execute("CREATE UNIQUE INDEX uq_rule_bike_code ON service_rule (bike_id, rule_code) "
                   "WHERE bike_id IS NOT NULL")
    setups = NEW_SETUPS if new else OLD_SETUPS
    names = "TUBE, TUBELESS, TUBULAR, ELECTRONIC or MECHANICAL" if new else "TUBE, TUBELESS or TUBULAR"
    for ev in ('INSERT', 'UPDATE'):
        op.execute(f"""
        CREATE TRIGGER trg_service_rule_requires_setup_{ev.lower()} BEFORE {ev} ON service_rule
        FOR EACH ROW WHEN NEW.requires_setup IS NOT NULL AND NEW.requires_setup NOT IN {setups}
        BEGIN SELECT RAISE(ABORT, 'INVALID: service_rule.requires_setup must be {names}'); END
        """)


def _rebuild(*, new: bool) -> None:
    for ev in ('insert', 'update'):
        op.execute(f"DROP TRIGGER IF EXISTS trg_service_rule_requires_setup_{ev}")
    _create("service_rule_new", new=new)
    if not new:   # downgrade: rules that only the new version understands cannot be kept
        op.execute("DELETE FROM service_rule WHERE bike_id IS NOT NULL OR component_type = 'BIKE' "
                   "OR trigger = 'ONCE_AFTER_INSTALL' OR requires_setup IN ('ELECTRONIC','MECHANICAL')")
    cols = COLUMNS + (", bike_id" if new else "")
    op.execute(f"INSERT INTO service_rule_new ({cols}) SELECT {COLUMNS}{', NULL' if new else ''} FROM service_rule")
    op.execute("DROP TABLE service_rule")
    op.execute("ALTER TABLE service_rule_new RENAME TO service_rule")
    _finish(new=new)


OLD_DISP = "('STORED','AWAITING_SERVICE','RETIRED','DISCARDED','SOLD','VOIDED')"
NEW_DISP = "('STORED','AWAITING_SERVICE','RETIRED','DISCARDED','SOLD','VOIDED','IN_USE')"


def _dispositions(allowed: str) -> None:
    for table in ("component", "component_disposition"):
        for ev in ("INSERT", "UPDATE"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_disposition_{ev.lower()}")
            op.execute(f"""
            CREATE TRIGGER trg_{table}_disposition_{ev.lower()} BEFORE {ev} ON {table}
            FOR EACH ROW WHEN NEW.disposition NOT IN {allowed}
            BEGIN SELECT RAISE(ABORT, 'INVALID: {table}.disposition must be one of {allowed.replace("'", "")}'); END
            """)


def upgrade() -> None:
    _rebuild(new=True)
    _dispositions(NEW_DISP)
    with op.batch_alter_table('reminder_snooze', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bike_id', sa.Integer(), nullable=True))
        batch_op.alter_column('component_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key('fk_reminder_snooze_bike', 'bike', ['bike_id'], ['id'])
        batch_op.create_index('ix_reminder_snooze_bike_id', ['bike_id'], unique=False)
    op.add_column('bike', sa.Column('shifting', sa.String(length=12), nullable=True))
    op.execute("UPDATE service_rule SET requires_setup = NULL, notes = 'Check at every tire change or yearly "
               "(tubes: tape covers the spoke holes; tubeless: it seals).' WHERE rule_code = 'RIM_TAPE_CHECK' "
               "AND component_type = 'RIM_TAPE' AND origin = 'DEFAULT'")
    op.execute("UPDATE service_rule SET interval_months = 12, warn_days = 30 WHERE rule_code = 'TIRE_CHECK' "
               "AND component_type = 'TIRE' AND origin = 'DEFAULT' AND interval_months IS NULL")
    op.execute("UPDATE service_rule SET interval_months = 18 WHERE rule_code = 'SHIFTER_COIN_CELLS' "
               "AND component_type = 'SHIFTERS' AND origin = 'DEFAULT' AND interval_months = 24")


def downgrade() -> None:
    op.execute("UPDATE component_disposition SET disposition = 'STORED' WHERE disposition = 'IN_USE'")
    op.execute("UPDATE component SET disposition = 'STORED' WHERE disposition = 'IN_USE'")
    _dispositions(OLD_DISP)
    op.drop_column('bike', 'shifting')
    op.execute("DELETE FROM reminder_snooze WHERE component_id IS NULL")
    with op.batch_alter_table('reminder_snooze', schema=None) as batch_op:
        batch_op.drop_index('ix_reminder_snooze_bike_id')
        batch_op.drop_constraint('fk_reminder_snooze_bike', type_='foreignkey')
        batch_op.drop_column('bike_id')
        batch_op.alter_column('component_id', existing_type=sa.Integer(), nullable=False)
    _rebuild(new=False)
