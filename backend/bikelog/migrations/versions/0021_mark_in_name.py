"""The mark is part of a part's name (Dirk 2026-11-02, DECISIONS 132).

Dirk: "this is name: Shimano XT CN-M8100 12-fach Kette, this is the mark: A, list it in the system as
Shimano XT CN-M8100 12-fach Kette [A]. we should apply the same logic to tires".

* A chain called "Name (B)" (the letter given by 0020) gets mark B and is called "Name [B]".
* Every other part with a mark gets " [mark]" after its name.
Only labels and marks change. A name that would clash with another part's is left as it was.
"""
import re

import sqlalchemy as sa
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

LETTER = re.compile(r"^(.*\S)\s+\(([A-Z])\)$")
SAME_NAME = ("TIRE", "INNER_TUBE")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, component_type, label, mark FROM component ORDER BY id")).fetchall()
    taken = {(t, label.lower()) for _id, t, label, _m in rows}
    for cid, ctype, label, mark in rows:
        new_label, new_mark = label, mark
        m = LETTER.match(label)
        if ctype == "CHAIN" and m and not mark:
            new_label, new_mark = f"{m.group(1)} [{m.group(2)}]", m.group(2)
        elif mark and not label.endswith(f"[{mark}]"):
            new_label = f"{label} [{mark}]"
        if new_label == label:
            continue
        if ctype not in SAME_NAME and (ctype, new_label.lower()) in taken:
            continue
        taken.discard((ctype, label.lower()))
        taken.add((ctype, new_label.lower()))
        conn.execute(sa.text("UPDATE component SET label = :l, mark = :m WHERE id = :i"),
                     {"l": new_label, "m": new_mark, "i": cid})


def downgrade() -> None:
    conn = op.get_bind()
    for cid, label, mark in conn.execute(sa.text(
            "SELECT id, label, mark FROM component WHERE mark IS NOT NULL")).fetchall():
        if label.endswith(f" [{mark}]"):
            conn.execute(sa.text("UPDATE component SET label = :l WHERE id = :i"),
                         {"l": label[: -len(mark) - 3], "i": cid})
