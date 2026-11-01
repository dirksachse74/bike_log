"""Incidents with several affected parts or body areas

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26 09:00:00

* journal_entry.incident_group: the entries of one incident (one per affected part or body area) share it.
  Existing incidents get a group of their own (their uuid).
* journal_entry.affected: what was affected when it is not a recorded part ("Numb hands", "Front tire").
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('journal_entry', sa.Column('incident_group', sa.String(length=36), nullable=True))
    op.add_column('journal_entry', sa.Column('affected', sa.Text(), nullable=True))
    op.create_index('ix_journal_entry_incident_group', 'journal_entry', ['incident_group'], unique=False)
    op.execute("UPDATE journal_entry SET incident_group = uuid WHERE incident_type IS NOT NULL")


def downgrade() -> None:
    # plain DROP COLUMN (SQLite 3.35+) keeps the table and its no-delete trigger
    op.drop_index('ix_journal_entry_incident_group', table_name='journal_entry')
    op.drop_column('journal_entry', 'affected')
    op.drop_column('journal_entry', 'incident_group')
