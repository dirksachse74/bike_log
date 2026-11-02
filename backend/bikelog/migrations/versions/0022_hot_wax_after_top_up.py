"""Hot wax is due a set distance after a liquid-wax top-up

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-02 10:00:00

Dirk 2026-11-02: "300km hot wax, followed by a liquid wax top-up, then a fresh hot wax after another 200km
… sometimes … i'll do a liquid wax top-up and then a fresh hot wax after 200km" (DECISIONS 133).

* service_rule.after_top_up_km; every hot-wax rule (type default and your own per chain) gets 200 km.
"""
from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('service_rule', sa.Column('after_top_up_km', sa.Float(), nullable=True))
    op.execute("UPDATE service_rule SET after_top_up_km = 200 WHERE action_code = 'WAX_HOT'")


def downgrade() -> None:
    with op.batch_alter_table('service_rule') as b:
        b.drop_column('after_top_up_km')
