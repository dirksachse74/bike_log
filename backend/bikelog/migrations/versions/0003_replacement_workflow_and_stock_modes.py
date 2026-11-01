"""Replacement workflow, spare-parts stock, work sessions with undo, consumable tracking modes

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 23:00:00

CREATE TABLE and plain ADD COLUMN only, except consumable_txn (no triggers) which is rebuilt to
allow the RETURN kind. Tables with protection triggers from 0001 are never rebuilt. New reference columns are soft references (no FK) because SQLite
cannot add a foreign key to an existing table without rebuilding it.
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

DISPOSITIONS = "('STORED','AWAITING_SERVICE','RETIRED','DISCARDED','SOLD','VOIDED')"


def upgrade() -> None:
    op.create_table('work_session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('performed_at', sa.String(length=20), nullable=False),
    sa.Column('performed_on', sa.String(length=10), nullable=False),
    sa.Column('bike_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.Column('undone_at', sa.String(length=20), nullable=True),
    sa.Column('undo_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['bike_id'], ['bike.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    op.create_table('component_disposition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('disposition', sa.String(length=20), nullable=False),
    sa.Column('previous_disposition', sa.String(length=20), nullable=True),
    sa.Column('effective_on', sa.String(length=10), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('work_session_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.Column('voided_at', sa.String(length=20), nullable=True),
    sa.ForeignKeyConstraint(['component_id'], ['component.id'], ),
    sa.ForeignKeyConstraint(['work_session_id'], ['work_session.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_component_disposition_component_id', 'component_disposition', ['component_id'])
    op.create_table('product_compatibility',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('bike_id', sa.Integer(), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['bike_id'], ['bike.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'bike_id', name='uq_product_bike')
    )
    op.create_index('ix_product_compatibility_product_id', 'product_compatibility', ['product_id'])

    op.add_column('component', sa.Column('disposition', sa.String(length=20), nullable=False,
                                         server_default='STORED'))
    op.add_column('component', sa.Column('disposition_on', sa.String(length=10), nullable=True))
    op.add_column('component', sa.Column('purchase_session_id', sa.Integer(), nullable=True))
    op.add_column('component', sa.Column('from_stock_txn_id', sa.Integer(), nullable=True))
    op.add_column('component', sa.Column('storage_location', sa.Text(), nullable=True))
    op.add_column('installation', sa.Column('removal_outcome', sa.String(length=20), nullable=True))
    op.add_column('installation', sa.Column('removal_undone_at', sa.String(length=20), nullable=True))
    op.add_column('installation', sa.Column('install_session_id', sa.Integer(), nullable=True))
    op.add_column('installation', sa.Column('removal_session_id', sa.Integer(), nullable=True))
    op.add_column('maintenance_event', sa.Column('work_session_id', sa.Integer(), nullable=True))
    op.create_index('ix_maintenance_event_work_session_id', 'maintenance_event', ['work_session_id'])
    op.add_column('consumable', sa.Column('tracking_mode', sa.String(length=8), nullable=False,
                                          server_default='BULK'))
    op.add_column('consumable', sa.Column('container_size', sa.Float(), nullable=True))
    op.add_column('consumable', sa.Column('component_type', sa.String(length=32), nullable=True))
    op.add_column('consumable', sa.Column('product_id', sa.Integer(), nullable=True))
    op.add_column('consumable', sa.Column('unit_note', sa.Text(), nullable=True))
    op.add_column('consumable', sa.Column('storage_location', sa.Text(), nullable=True))
    op.add_column('consumable', sa.Column('min_stock', sa.Float(), nullable=True))
    with op.batch_alter_table('consumable_txn', recreate='always') as b:
        b.add_column(sa.Column('work_session_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('component_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('packages', sa.Integer(), nullable=True))
        b.add_column(sa.Column('voided_at', sa.String(length=20), nullable=True))
        b.drop_constraint('ck_consumable_txn_kind', type_='check')
        b.create_check_constraint('ck_consumable_txn_kind', "kind IN ('PURCHASE','USE','RETURN','ADJUST')")
        b.create_index('ix_consumable_txn_work_session_id', ['work_session_id'])

    # Existing retired parts keep their meaning; their disposition history starts here.
    op.execute("UPDATE component SET disposition = 'RETIRED', disposition_on = retired_on WHERE status = 'RETIRED'")
    op.execute("INSERT INTO component_disposition (component_id, disposition, previous_disposition, effective_on, "
               "note, created_at) "
               "SELECT id, 'RETIRED', 'STORED', COALESCE(retired_on, substr(updated_at, 1, 10)), retire_reason, "
               "strftime('%Y-%m-%dT%H:%M:%SZ','now') FROM component WHERE status = 'RETIRED'")

    for table, col, allowed in (("component", "disposition", DISPOSITIONS),
                                ("component_disposition", "disposition", DISPOSITIONS),
                                ("consumable", "tracking_mode", "('COUNTED','BULK')")):
        for ev in ("INSERT", "UPDATE"):
            op.execute(f"""
            CREATE TRIGGER trg_{table}_{col}_{ev.lower()} BEFORE {ev} ON {table}
            FOR EACH ROW WHEN NEW.{col} NOT IN {allowed}
            BEGIN SELECT RAISE(ABORT, 'INVALID: {table}.{col} must be one of {allowed.replace("'", "")}'); END
            """)
    op.execute("""
    CREATE TRIGGER trg_component_disposition_no_delete BEFORE DELETE ON component_disposition
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: disposition history cannot be deleted'); END
    """)


def downgrade() -> None:
    for name in ("component_disposition_no_delete",
                 "component_disposition_insert", "component_disposition_update",
                 "component_disposition_disposition_insert", "component_disposition_disposition_update",
                 "consumable_tracking_mode_insert", "consumable_tracking_mode_update"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{name}")
    with op.batch_alter_table('consumable_txn') as b:
        b.drop_index('ix_consumable_txn_work_session_id')
        b.drop_column('voided_at')
        b.drop_column('packages')
        b.drop_column('component_id')
        b.drop_column('work_session_id')
    with op.batch_alter_table('consumable') as b:
        b.drop_column('min_stock')
        b.drop_column('storage_location')
        b.drop_column('unit_note')
        b.drop_column('product_id')
        b.drop_column('component_type')
        b.drop_column('container_size')
        b.drop_column('tracking_mode')
    with op.batch_alter_table('maintenance_event') as b:
        b.drop_index('ix_maintenance_event_work_session_id')
        b.drop_column('work_session_id')
    with op.batch_alter_table('installation') as b:
        b.drop_column('removal_undone_at')
        b.drop_column('removal_session_id')
        b.drop_column('install_session_id')
        b.drop_column('removal_outcome')
    with op.batch_alter_table('component') as b:
        b.drop_column('storage_location')
        b.drop_column('from_stock_txn_id')
        b.drop_column('purchase_session_id')
        b.drop_column('disposition_on')
        b.drop_column('disposition')
    op.drop_index('ix_component_disposition_component_id', 'component_disposition')
    op.drop_index('ix_product_compatibility_product_id', 'product_compatibility')
    op.drop_table('product_compatibility')
    op.drop_table('component_disposition')
    op.drop_table('work_session')
