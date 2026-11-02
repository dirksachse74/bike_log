"""Tires and inner tubes may share a name; chains are told apart by letters

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-02 09:30:00

Dirk 2026-11-02: "some parts are so generic, i dont like the idea of an individual name. for example, tires.
i just want to add an tire and enter its product name. i dont want to see (2), (3) etc. same for inner tubes.
For chains it will make sense but I like letters more there (A),(B),(C)".

* The unique (component_type, label) table constraint becomes a unique index that leaves out TIRE and
  INNER_TUBE (catalog.SAME_NAME_TYPES), so two "GP5000" tires are fine. SQLite cannot drop a table constraint,
  so the component table is rebuilt from its own stored definition (same columns, indexes and triggers);
  foreign keys are checked at the end of the migration (defer_foreign_keys), nothing points elsewhere.
* Existing names: a tire / tube "GP5000 (2)" becomes "GP5000"; a chain "Chain A (2)" becomes "Chain A (B)",
  "(3)" → "(C)" and so on.
"""
import re

from alembic import op
import sqlalchemy as sa


revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

SAME_NAME = ('TIRE', 'INNER_TUBE')
UNIQUE_SQL = re.compile(r",\s*CONSTRAINT uq_component_type_label UNIQUE \(component_type, label\)", re.I)
SUFFIX = re.compile(r"^(.*\S)\s+\((\d+)\)$")


def _rebuild(table_sql_change) -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    table_sql = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name='component'").scalar()
    extras = [r[0] for r in conn.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE tbl_name='component' AND type IN ('index','trigger') "
        "AND sql IS NOT NULL AND name <> 'uq_component_type_label'")]
    new_sql = table_sql_change(table_sql)
    new_sql = re.sub(r'^CREATE TABLE "?component"?', 'CREATE TABLE component_new', new_sql)
    conn.exec_driver_sql(new_sql)
    cols = ", ".join(f'"{r[1]}"' for r in conn.exec_driver_sql("PRAGMA table_info(component)"))
    conn.exec_driver_sql(f"INSERT INTO component_new ({cols}) SELECT {cols} FROM component")
    conn.exec_driver_sql("DROP TABLE component")
    conn.exec_driver_sql("ALTER TABLE component_new RENAME TO component")
    for sql in extras:
        conn.exec_driver_sql(sql)


def upgrade() -> None:
    def drop_unique(sql: str) -> str:
        out, n = UNIQUE_SQL.subn("", sql)
        if n != 1:
            raise RuntimeError("component table: unique (component_type, label) constraint not found")
        return out
    _rebuild(drop_unique)
    op.execute("CREATE UNIQUE INDEX uq_component_type_label ON component (component_type, label) "
               f"WHERE component_type NOT IN {SAME_NAME!r}")
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, component_type, label FROM component "
                                "WHERE component_type IN ('TIRE','INNER_TUBE','CHAIN')")).fetchall()
    taken = {(t, label.lower()) for _id, t, label in rows}
    for cid, ctype, label in rows:
        m = SUFFIX.match(label)
        if not m:
            continue
        base, n = m.group(1), int(m.group(2))
        if ctype in SAME_NAME:
            new = base
        elif 2 <= n <= 26:
            new = f"{base} ({chr(ord('A') + n - 1)})"
            if (ctype, new.lower()) in taken:
                continue
        else:
            continue
        taken.add((ctype, new.lower()))
        conn.execute(sa.text("UPDATE component SET label = :l WHERE id = :i"), {"l": new, "i": cid})


def downgrade() -> None:
    # names made equal cannot be told apart again automatically: number the duplicates back
    conn = op.get_bind()
    seen: dict[tuple, int] = {}
    for cid, ctype, label in conn.execute(sa.text(
            "SELECT id, component_type, label FROM component ORDER BY id")).fetchall():
        key = (ctype, label.lower())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            conn.execute(sa.text("UPDATE component SET label = :l WHERE id = :i"),
                         {"l": f"{label} ({seen[key]})", "i": cid})
    op.execute("DROP INDEX IF EXISTS uq_component_type_label")
    _rebuild(lambda sql: re.sub(r"\)\s*$", ", CONSTRAINT uq_component_type_label UNIQUE (component_type, label))",
                                sql.rstrip(), count=1))
