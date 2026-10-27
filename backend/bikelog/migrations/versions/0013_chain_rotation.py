"""Chains you rotate: a mark to tell identical parts apart, and the bike whose chain rotation a chain is in

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26 12:30:00

* component.mark: how the part is marked physically ("1 punch dot next to the quick link"), shown next to
  its name wherever identical parts must be told apart.
* component.rotation_bike_id: the bike whose chain rotation this chain belongs to (set when a chain is
  first installed on a bike, or by hand). NULL = not in a rotation.
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('component', sa.Column('mark', sa.Text(), nullable=True))
    op.execute("ALTER TABLE component ADD COLUMN rotation_bike_id INTEGER REFERENCES bike (id)")
    # chains already on a bike, or last taken off one, join that bike's rotation
    op.execute("""
        UPDATE component SET rotation_bike_id = (
            SELECT i.bike_id FROM installation i
            WHERE i.component_id = component.id AND i.bike_id IS NOT NULL AND i.voided_at IS NULL
            ORDER BY i.installed_utc DESC LIMIT 1)
        WHERE component_type = 'CHAIN' AND status = 'ACTIVE'
    """)


def downgrade() -> None:
    op.drop_column('component', 'rotation_bike_id')
    op.drop_column('component', 'mark')
