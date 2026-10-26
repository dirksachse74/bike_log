"""Frame and fork as parts: a warranty date on parts and the "returned under warranty" outcome

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26 14:30:00

* component.warranty_until: the last day of the warranty (any part; frames above all).
* Disposition WARRANTY_RETURN: a part sent back under warranty (out of use, history kept).
Existing bikes get their frame and fork parts on the next start (services/frames.py), not here: the
installation and usage bookkeeping lives in Python.
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

OLD_DISP = "('STORED','AWAITING_SERVICE','RETIRED','DISCARDED','SOLD','VOIDED','IN_USE')"
NEW_DISP = "('STORED','AWAITING_SERVICE','RETIRED','DISCARDED','SOLD','VOIDED','IN_USE','WARRANTY_RETURN')"


def _dispositions(allowed: str) -> None:
    for table in ("component", "component_disposition"):
        for ev in ("INSERT", "UPDATE"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_disposition_{ev.lower()}")
            op.execute(f"""
            CREATE TRIGGER trg_{table}_disposition_{ev.lower()} BEFORE {ev} ON {table}
            FOR EACH ROW WHEN NEW.disposition NOT IN {allowed}
            BEGIN SELECT RAISE(ABORT, 'INVALID: {table}.disposition must be one of {allowed.replace("'", "")}'); END
            """)


def upgrade() -> None:
    op.add_column('component', sa.Column('warranty_until', sa.String(length=10), nullable=True))
    _dispositions(NEW_DISP)


def downgrade() -> None:
    _dispositions(OLD_DISP)
    op.drop_column('component', 'warranty_until')
