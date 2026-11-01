"""Prices (bike purchase price and date, reference price on products) and the journal

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 16:30:00

Plain ADD COLUMN and CREATE TABLE only; no table is rebuilt. Running cost is derived from existing
records (component prices, stock purchases, service costs) and is not stored. Journal entries cannot be
deleted (trigger); a wrong entry is voided.
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bike', sa.Column('purchase_price_cents', sa.Integer(), nullable=True))
    op.add_column('bike', sa.Column('purchase_date', sa.String(length=10), nullable=True))
    op.add_column('product', sa.Column('list_price_cents', sa.Integer(), nullable=True))
    op.create_table('journal_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('bike_id', sa.Integer(), nullable=True),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('entry_on', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('resolved_on', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.Column('updated_at', sa.String(length=20), nullable=True),
    sa.Column('voided_at', sa.String(length=20), nullable=True),
    sa.Column('void_reason', sa.Text(), nullable=True),
    sa.CheckConstraint("kind IN ('NOTE','ISSUE')", name='ck_journal_kind'),
    sa.CheckConstraint('bike_id IS NOT NULL OR component_id IS NOT NULL', name='ck_journal_target'),
    sa.ForeignKeyConstraint(['bike_id'], ['bike.id'], ),
    sa.ForeignKeyConstraint(['component_id'], ['component.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    op.create_index('ix_journal_entry_bike_id', 'journal_entry', ['bike_id'])
    op.create_index('ix_journal_entry_component_id', 'journal_entry', ['component_id'])
    op.execute("""
    CREATE TRIGGER trg_journal_entry_no_delete BEFORE DELETE ON journal_entry
    BEGIN SELECT RAISE(ABORT, 'PROTECTED: journal entries cannot be deleted; void them instead'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_journal_entry_no_delete")
    op.drop_index('ix_journal_entry_component_id', table_name='journal_entry')
    op.drop_index('ix_journal_entry_bike_id', table_name='journal_entry')
    op.drop_table('journal_entry')
    with op.batch_alter_table('product') as b:
        b.drop_column('list_price_cents')
    with op.batch_alter_table('bike') as b:
        b.drop_column('purchase_date')
        b.drop_column('purchase_price_cents')
