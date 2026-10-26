"""Parts sent away for service or repair, and what came back

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26 15:00:00

* service_order: a part sent to a shop or the maker (from where, why, linked incident) and its return
  (outcome: paid repair, warranty repair, warranty replacement, not repairable; cost, receipt, the
  REPAIR event that carries the cost, the replacement part). Never deleted.
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('service_order',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('bike_id', sa.Integer(), nullable=True),
    sa.Column('from_bike_id', sa.Integer(), nullable=True),
    sa.Column('from_parent_id', sa.Integer(), nullable=True),
    sa.Column('from_slot', sa.String(length=40), nullable=True),
    sa.Column('sent_at', sa.String(length=20), nullable=False),
    sa.Column('sent_on', sa.String(length=10), nullable=False),
    sa.Column('shop', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('incident_group', sa.String(length=36), nullable=True),
    sa.Column('send_session_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=8), nullable=False),
    sa.Column('returned_at', sa.String(length=20), nullable=True),
    sa.Column('returned_on', sa.String(length=10), nullable=True),
    sa.Column('outcome', sa.String(length=20), nullable=True),
    sa.Column('cost_cents', sa.Integer(), nullable=True),
    sa.Column('receipt_ref', sa.Text(), nullable=True),
    sa.Column('return_notes', sa.Text(), nullable=True),
    sa.Column('return_session_id', sa.Integer(), nullable=True),
    sa.Column('event_id', sa.Integer(), nullable=True),
    sa.Column('replacement_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.CheckConstraint("status IN ('OUT','BACK','VOIDED')", name='ck_service_order_status'),
    sa.CheckConstraint('cost_cents IS NULL OR cost_cents >= 0', name='ck_service_order_cost'),
    sa.ForeignKeyConstraint(['bike_id'], ['bike.id'], ),
    sa.ForeignKeyConstraint(['component_id'], ['component.id'], ),
    sa.ForeignKeyConstraint(['event_id'], ['maintenance_event.id'], ),
    sa.ForeignKeyConstraint(['from_bike_id'], ['bike.id'], ),
    sa.ForeignKeyConstraint(['from_parent_id'], ['component.id'], ),
    sa.ForeignKeyConstraint(['replacement_id'], ['component.id'], ),
    sa.ForeignKeyConstraint(['return_session_id'], ['work_session.id'], ),
    sa.ForeignKeyConstraint(['send_session_id'], ['work_session.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    op.create_index('ix_service_order_component_id', 'service_order', ['component_id'])
    op.execute("""
    CREATE TRIGGER trg_service_order_no_delete BEFORE DELETE ON service_order
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: service orders cannot be deleted; they are voided instead'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_service_order_no_delete")
    op.drop_index('ix_service_order_component_id', 'service_order')
    op.drop_table('service_order')
