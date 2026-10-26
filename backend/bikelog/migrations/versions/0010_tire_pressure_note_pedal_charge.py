"""Tire pressure note, power-pedal charge every 80 ride hours

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26 08:00:00

* component.pressure_note: free text on a tire ("4.8 bar"), shown on the bike page. A note, no reminder.
* The power-pedal charge default (POWER_PEDALS_CHARGE) goes from 50 to 80 ride hours, only where it was
  never edited (origin DEFAULT, still 50 h).
The yearly full service (BIKE_FULL_SERVICE) is a new default rule; it is added at startup like other defaults.
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('component', sa.Column('pressure_note', sa.Text(), nullable=True))
    op.execute("UPDATE service_rule SET interval_hours = 80 WHERE rule_code = 'POWER_PEDALS_CHARGE' "
               "AND component_type = 'POWER_METER_PEDALS' AND origin = 'DEFAULT' AND interval_hours = 50")


def downgrade() -> None:
    op.execute("UPDATE service_rule SET interval_hours = 50 WHERE rule_code = 'POWER_PEDALS_CHARGE' "
               "AND component_type = 'POWER_METER_PEDALS' AND origin = 'DEFAULT' AND interval_hours = 80")
    with op.batch_alter_table('component', schema=None) as batch_op:
        batch_op.drop_column('pressure_note')
