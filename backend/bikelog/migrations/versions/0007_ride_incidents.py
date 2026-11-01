"""Ride incidents and ride conditions

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25 23:00:00

Nullable columns only (ADD COLUMN; protected tables are not rebuilt):
* ride.conditions: DRY / WET, set by you (imports never touch it);
* journal_entry.ride_id and journal_entry.incident_type: an incident (flat, crash, defect, ...) is a
  journal issue linked to the ride it happened on and to the affected part or bike.
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ride', sa.Column('conditions', sa.String(length=8), nullable=True))
    op.execute("ALTER TABLE journal_entry ADD COLUMN ride_id INTEGER REFERENCES ride (id)")
    op.add_column('journal_entry', sa.Column('incident_type', sa.String(length=16), nullable=True))
    op.create_index('ix_journal_entry_ride_id', 'journal_entry', ['ride_id'])


def downgrade() -> None:
    op.drop_index('ix_journal_entry_ride_id', table_name='journal_entry')
    with op.batch_alter_table('journal_entry') as b:
        b.drop_column('incident_type')
        b.drop_column('ride_id')
    with op.batch_alter_table('ride') as b:
        b.drop_column('conditions')
