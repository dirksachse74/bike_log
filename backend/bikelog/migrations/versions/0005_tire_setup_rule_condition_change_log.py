"""Tire setup on wheels, setup condition on service rules, change log

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25 18:30:00

Plain ADD COLUMN and CREATE TABLE only; no table is rebuilt. The change log starts empty: it records
changes made from this version on. Change-log rows cannot be updated or deleted (triggers).
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

SETUPS = "('TUBE','TUBELESS','TUBULAR')"


def upgrade() -> None:
    op.add_column('component', sa.Column('tire_setup', sa.String(length=12), nullable=True))
    op.add_column('service_rule', sa.Column('requires_setup', sa.String(length=12), nullable=True))
    for table, col in (('component', 'tire_setup'), ('service_rule', 'requires_setup')):
        for ev in ('INSERT', 'UPDATE'):
            op.execute(f"""
            CREATE TRIGGER trg_{table}_{col}_{ev.lower()} BEFORE {ev} ON {table}
            FOR EACH ROW WHEN NEW.{col} IS NOT NULL AND NEW.{col} NOT IN {SETUPS}
            BEGIN SELECT RAISE(ABORT, 'INVALID: {table}.{col} must be TUBE, TUBELESS or TUBULAR'); END
            """)
    op.create_table('change_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('changed_at', sa.String(length=20), nullable=False),
    sa.Column('bike_id', sa.Integer(), nullable=True),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('field', sa.String(length=64), nullable=True),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('via', sa.String(length=64), nullable=True),
    sa.CheckConstraint('bike_id IS NOT NULL OR component_id IS NOT NULL', name='ck_change_log_target'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_change_log_bike_id', 'change_log', ['bike_id'])
    op.create_index('ix_change_log_component_id', 'change_log', ['component_id'])
    op.execute("""
    CREATE TRIGGER trg_change_log_no_delete BEFORE DELETE ON change_log
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: the change log cannot be deleted'); END
    """)
    op.execute("""
    CREATE TRIGGER trg_change_log_no_update BEFORE UPDATE ON change_log
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: the change log cannot be changed'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_change_log_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_change_log_no_delete")
    op.drop_index('ix_change_log_component_id', table_name='change_log')
    op.drop_index('ix_change_log_bike_id', table_name='change_log')
    op.drop_table('change_log')
    for table, col in (('component', 'tire_setup'), ('service_rule', 'requires_setup')):
        for ev in ('insert', 'update'):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_{col}_{ev}")
    with op.batch_alter_table('service_rule') as b:
        b.drop_column('requires_setup')
    with op.batch_alter_table('component') as b:
        b.drop_column('tire_setup')
