"""Pick lists (shops first) and where things were bought

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-01 12:00:00

* pick_list_item: reusable names for dropdowns (list_code SHOP), managed in Settings → Lists.
* shop on bike, component and consumable_txn (purchases); bundles (merchant) and service orders (shop)
  already had one. The SHOP list starts with the shop names already entered there.
"""
from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('pick_list_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('list_code', sa.String(length=24), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('hidden_at', sa.String(length=20), nullable=True),
    sa.Column('merged_into_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['merged_into_id'], ['pick_list_item.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid'),
    sa.UniqueConstraint('list_code', 'name', name='uq_pick_list_item')
    )
    op.create_index('ix_pick_list_item_list_code', 'pick_list_item', ['list_code'])
    for table in ('bike', 'component', 'consumable_txn'):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column('shop', sa.Text(), nullable=True))
    conn = op.get_bind()
    names: dict[str, str] = {}
    for sql in ("SELECT merchant FROM purchase_bundle WHERE merchant IS NOT NULL",
                "SELECT shop FROM service_order WHERE shop IS NOT NULL"):
        for (n,) in conn.execute(sa.text(sql)):
            n = (n or '').strip()
            if n and n.lower() not in names:
                names[n.lower()] = n
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for n in sorted(names.values(), key=str.lower):
        conn.execute(sa.text("INSERT INTO pick_list_item (uuid, list_code, name, created_at) VALUES (:u, 'SHOP', :n, :t)"),
                     {"u": str(uuid.uuid4()), "n": n, "t": now})


def downgrade() -> None:
    for table in ('consumable_txn', 'component', 'bike'):
        with op.batch_alter_table(table) as b:
            b.drop_column('shop')
    op.drop_index('ix_pick_list_item_list_code', table_name='pick_list_item')
    op.drop_table('pick_list_item')
