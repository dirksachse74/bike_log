"""Repairs of incidents: what was done about each affected part

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26 10:00:00

* journal_entry.repair: REPLACED or REPAIRED (a patched tube, an adjusted derailleur); NULL = nothing yet.
* journal_entry.repair_text / repaired_on: what was done and when (ride date on the road, or later at home).
* journal_entry.repair_session_id: the work session holding the part change, stock use or patch event, so the
  fix is undone with that session.
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('journal_entry', sa.Column('repair', sa.String(length=12), nullable=True))
    op.add_column('journal_entry', sa.Column('repair_text', sa.Text(), nullable=True))
    op.add_column('journal_entry', sa.Column('repaired_on', sa.String(length=10), nullable=True))
    op.execute("ALTER TABLE journal_entry ADD COLUMN repair_session_id INTEGER REFERENCES work_session (id)")


def downgrade() -> None:
    # plain DROP COLUMN (SQLite 3.35+) keeps the table and its no-delete trigger
    op.drop_column('journal_entry', 'repair_session_id')
    op.drop_column('journal_entry', 'repaired_on')
    op.drop_column('journal_entry', 'repair_text')
    op.drop_column('journal_entry', 'repair')
