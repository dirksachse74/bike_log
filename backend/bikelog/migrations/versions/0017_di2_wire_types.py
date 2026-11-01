"""Di2 wires and junction boxes are groupset parts

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-01 18:00:00

Wired Di2 wires used to be imported (groupset import) and added as type OTHER, so they showed under
"Other" instead of the groupset (Dirk 2026-11-01). New types DI2_WIRES and DI2_JUNCTION (category
Controls, part of the groupset). Existing "Other" parts that are Di2 wires or a junction box get the new
type: those in the DI2_WIRES slot, or whose name / product names them (Di2 wire, EW-SD..., junction,
EW-JC..., EW-RS910). Their products follow. Nothing else changes (km, history, installations stay).
"""
from alembic import op


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

WIRE = ("lower(c.label) LIKE '%di2%wire%' OR lower(c.label) LIKE '%ew-sd%' "
        "OR lower(coalesce(p.model, '')) LIKE '%ew-sd%' OR lower(coalesce(p.model, '')) LIKE '%di2%wire%' "
        "OR c.id IN (SELECT component_id FROM installation WHERE slot = 'DI2_WIRES')")
JUNCTION = ("lower(c.label) LIKE '%junction%' OR lower(c.label) LIKE '%ew-jc%' OR lower(c.label) LIKE '%ew-rs910%' "
            "OR lower(coalesce(p.model, '')) LIKE '%ew-jc%' OR lower(coalesce(p.model, '')) LIKE '%ew-rs910%' "
            "OR lower(coalesce(p.model, '')) LIKE '%junction%'")


def _retype(conn, new: str, cond: str) -> None:
    ids = [r[0] for r in conn.exec_driver_sql(
        f"SELECT c.id FROM component c LEFT JOIN product p ON p.id = c.product_id "
        f"WHERE c.component_type = 'OTHER' AND ({cond})")]
    for cid in ids:
        conn.exec_driver_sql("UPDATE component SET component_type = ? WHERE id = ?", (new, cid))
        conn.exec_driver_sql("UPDATE product SET component_type = ? WHERE component_type = 'OTHER' AND id = "
                             "(SELECT product_id FROM component WHERE id = ?)", (new, cid))


def upgrade() -> None:
    conn = op.get_bind()
    _retype(conn, "DI2_WIRES", WIRE)
    _retype(conn, "DI2_JUNCTION", JUNCTION)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("UPDATE component SET component_type = 'OTHER' "
                         "WHERE component_type IN ('DI2_WIRES', 'DI2_JUNCTION')")
    conn.exec_driver_sql("UPDATE product SET component_type = 'OTHER' "
                         "WHERE component_type IN ('DI2_WIRES', 'DI2_JUNCTION')")
