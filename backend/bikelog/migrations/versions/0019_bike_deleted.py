"""Bikes deleted for good

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-02 09:00:00

* bike.deleted_at: set when a bike is deleted for good (Settings: Bike → Retire or delete → Delete for good).
  The bike, its rides and its history are kept in the file (append-only history) but shown nowhere.
"""
from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bike', sa.Column('deleted_at', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bike') as b:
        b.drop_column('deleted_at')
