"""Who did the work: a bike shop on maintenance entries

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-01 21:30:00

* maintenance_event.shop: the bike shop that did the work (SHOP pick list), empty = done yourself.
"""
from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('maintenance_event') as b:
        b.add_column(sa.Column('shop', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('maintenance_event') as b:
        b.drop_column('shop')
