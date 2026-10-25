"""Purchase bundles (parts bought together at one price, e.g. a groupset)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25 22:30:00

New table plus one nullable column on component (ADD COLUMN; component is not rebuilt). Bundles cannot
be deleted (trigger); a wrong bundle is voided.
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('purchase_bundle',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('merchant', sa.Text(), nullable=True),
    sa.Column('purchased_on', sa.String(length=10), nullable=True),
    sa.Column('price_cents', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('work_session_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.Column('updated_at', sa.String(length=20), nullable=False),
    sa.Column('voided_at', sa.String(length=20), nullable=True),
    sa.Column('void_reason', sa.Text(), nullable=True),
    sa.CheckConstraint('price_cents IS NULL OR price_cents >= 0', name='ck_bundle_price'),
    sa.ForeignKeyConstraint(['work_session_id'], ['work_session.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    # SQLite cannot add a foreign key with ALTER TABLE ADD COLUMN; REFERENCES in the column definition
    # is allowed and enforced (foreign_keys = ON).
    op.execute("ALTER TABLE component ADD COLUMN bundle_id INTEGER REFERENCES purchase_bundle (id)")
    op.create_index('ix_component_bundle_id', 'component', ['bundle_id'])
    op.execute("""
    CREATE TRIGGER trg_purchase_bundle_no_delete BEFORE DELETE ON purchase_bundle
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: bundles cannot be deleted; void them instead'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_bundle_no_delete")
    op.drop_index('ix_component_bundle_id', table_name='component')
    with op.batch_alter_table('component') as b:
        b.drop_column('bundle_id')
    op.drop_table('purchase_bundle')
