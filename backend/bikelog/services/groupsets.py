"""Groupset import: create every component of a groupset in one work session.

Templates are data (bikelog.groupset_templates). Importing one creates a product per model (reusing an
existing product with the same maker and model) and a physical component per item. With a bike, each
part goes to its position: on the bike, on the wheel installed there (cassette, rotors) or on another new
part (chainrings on the crankset, quick link on the chain). A position that is already taken either keeps
the old part (the new one becomes a spare) or replaces it; the old part's outcome is recorded as usual.
Everything shares one work session, so the whole import can be undone in one step.
"""
from __future__ import annotations

import string

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES, DISPOSITIONS
from bikelog.groupset_templates import TEMPLATES
from bikelog.models import Component, Installation, Product
from bikelog.services import inventory as inv
from bikelog.services.errors import DomainError, NotFound

OCCUPIED_MODES = {"KEEP": "Keep the current part; the new one becomes a spare",
                  "REPLACE": "Replace the current part with the new one"}


def get_template(code: str) -> dict:
    t = TEMPLATES.get(code)
    if not t:
        raise NotFound(f"Unknown groupset template {code!r}")
    return t


def _fill(value, variables: dict):
    if isinstance(value, str):
        return string.Formatter().vformat(value, (), variables)
    if isinstance(value, dict):
        return {k: _fill(v, variables) for k, v in value.items()}
    return value


def choose(template: dict, options: dict | None) -> tuple[dict, dict]:
    """Resolve option values (defaults where missing). Returns (chosen values, placeholder variables)."""
    options = dict(options or {})
    chosen, variables = {}, {}
    for opt in template["options"]:
        value = str(options.pop(opt["key"], opt["default"]))
        choice = next((c for c in opt["choices"] if c["value"] == value), None)
        if choice is None:
            allowed = ", ".join(c["value"] for c in opt["choices"])
            raise DomainError(f"{opt['label']}: {value!r} is not offered (choose {allowed})")
        chosen[opt["key"]] = value
        variables.update(choice["vars"])
    if options:
        raise DomainError(f"Unknown options: {', '.join(options)}")
    return chosen, variables


def items(template: dict, chosen: dict, variables: dict) -> list[dict]:
    """The template's items that apply to these choices, with placeholders filled in."""
    out = []
    for it in template["items"]:
        when = it.get("when") or {}
        if any(chosen.get(k) not in v for k, v in when.items()):
            continue
        out.append({"key": it["key"], "type": it["type"], "name": _fill(it["name"], variables),
                    "model": _fill(it["model"], variables), "specs": _fill(it.get("specs", {}), variables),
                    "mount": it["mount"], "default": it.get("default", True)})
    return out


def describe(template: dict) -> dict:
    chosen, variables = choose(template, None)
    return {
        "code": template["code"], "name": template["name"], "maker": template["maker"],
        "series": template["series"], "speeds": template["speeds"], "notes": template.get("notes"),
        "source": template["source"], "checked_on": template.get("checked_on"),
        "verified": template["verified"], "label_prefix": template.get("label_prefix", template["series"]),
        "options": [{"key": o["key"], "label": o["label"], "default": o["default"],
                     "choices": [{"value": c["value"], "label": c["label"]} for c in o["choices"]]}
                    for o in template["options"]],
        "items": [{"key": i["key"], "type": i["type"], "type_name": COMPONENT_TYPES[i["type"]].name,
                   "name": i["name"], "default": i.get("default", True), "when": i.get("when")}
                  for i in template["items"]],
        "occupied_modes": [{"code": k, "label": v} for k, v in OCCUPIED_MODES.items()],
    }


def list_templates() -> list[dict]:
    return [describe(t) for t in TEMPLATES.values()]


def _open_in(session: Session, *, slot: str, bike_id: int | None = None,
             parent_id: int | None = None) -> Installation | None:
    q = select(Installation).where(Installation.voided_at.is_(None), Installation.removed_utc.is_(None),
                                   Installation.slot == slot)
    q = q.where(Installation.bike_id == bike_id) if bike_id is not None else q.where(
        Installation.parent_component_id == parent_id)
    return session.scalar(q)


def _find_product(session: Session, maker: str, model: str, component_type: str) -> Product | None:
    return session.scalar(select(Product).where(
        Product.component_type == component_type, func.lower(Product.maker) == maker.lower(),
        func.lower(Product.model) == model.lower()).order_by(Product.id))


def _unique_label(session: Session, component_type: str, base: str, taken: set[str]) -> str:
    label, n = base, 2
    while label.lower() in taken or session.scalar(select(Component.id).where(
            Component.component_type == component_type, func.lower(Component.label) == label.lower())):
        label, n = f"{base} ({n})", n + 1
    taken.add(label.lower())
    return label


def plan(session: Session, code: str, *, bike_id: int | None = None, options: dict | None = None,
         include: list[str] | None = None, label_prefix: str | None = None, occupied: str = "KEEP") -> dict:
    """What an import would do, item by item, without changing anything."""
    template = get_template(code)
    if occupied not in OCCUPIED_MODES:
        raise DomainError(f"occupied must be one of {', '.join(OCCUPIED_MODES)}")
    bike = inv.get_bike(session, bike_id) if bike_id is not None else None
    if bike and bike.status == "RETIRED":
        raise DomainError(f"{bike.name} is retired")
    chosen, variables = choose(template, options)
    all_items = items(template, chosen, variables)
    keys = {i["key"] for i in all_items}
    if include is not None:
        unknown = set(include) - {i["key"] for i in template["items"]}
        if unknown:
            raise DomainError(f"Unknown items: {', '.join(sorted(unknown))}")
        selected = [i for i in all_items if i["key"] in set(include)]
    else:
        selected = [i for i in all_items if i["default"]]
    if not selected:
        raise DomainError("Pick at least one part to add")
    selected_keys = {i["key"] for i in selected}
    prefix = (label_prefix or template.get("label_prefix") or template["series"]).strip()
    taken: set[str] = set()
    rows = []
    for it in selected:
        mount = it["mount"]
        base = f"{prefix} {it['name']}" + (f" ({bike.name})" if bike else "")
        product = _find_product(session, template["maker"], it["model"], it["type"])
        row = {"key": it["key"], "type": it["type"], "type_name": COMPONENT_TYPES[it["type"]].name,
               "model": it["model"], "specs": it["specs"],
               "label": _unique_label(session, it["type"], base, taken),
               "product_id": product.id if product else None, "product_exists": product is not None,
               "list_price_cents": product.list_price_cents if product else None,
               "action": "SPARE", "slot": mount["slot"], "bike_id": None, "parent_key": None,
               "parent_component_id": None, "replaces_component_id": None, "text": "Added as a spare"}
        if bike is None:
            row["text"] = "Added as a spare (no bike chosen)"
            rows.append(row)
            continue
        where_text = bike.name
        occupant = None
        if "parent" in mount:
            if mount["parent"] not in selected_keys:
                name = next((i["name"] for i in all_items if i["key"] == mount["parent"]), mount["parent"])
                row["text"] = (f"Added as a spare: it goes on the new {name}, which is not part of this import"
                               if mount["parent"] in keys else "Added as a spare")
                rows.append(row)
                continue
            parent_row = next(r for r in rows if r["key"] == mount["parent"])
            row.update(action="INSTALL", parent_key=mount["parent"],
                       text=f"Mounted on {parent_row['label']}")
            rows.append(row)
            continue
        if "wheel" in mount:
            wheel_inst = _open_in(session, bike_id=bike.id, slot=mount["wheel"])
            if wheel_inst is None:
                row["text"] = (f"Added as a spare: {bike.name} has no {mount['wheel'].replace('_', ' ').lower()} "
                               "installed. Install it on the wheel later.")
                rows.append(row)
                continue
            wheel = session.get(Component, wheel_inst.component_id)
            row["parent_component_id"] = wheel.id
            where_text = wheel.label
            occupant = _open_in(session, parent_id=wheel.id, slot=mount["slot"])
        else:
            row["bike_id"] = bike.id
            occupant = _open_in(session, bike_id=bike.id, slot=mount["slot"])
        slot_text = mount["slot"].replace("_", " ").lower()
        if occupant is None:
            row.update(action="INSTALL", text=f"Installed on {where_text} ({slot_text})")
        else:
            old = session.get(Component, occupant.component_id)
            if occupied == "REPLACE":
                outcome = COMPONENT_TYPES[old.component_type].removed_default
                row.update(action="REPLACE", replaces_component_id=old.id, replaces_label=old.label,
                           old_outcome=outcome,
                           text=f"Replaces {old.label} on {where_text}; {old.label} → "
                                f"{DISPOSITIONS[outcome].lower()}")
            else:
                row.update(text=f"Added as a spare: {where_text} ({slot_text}) already has {old.label}",
                           occupied_by=old.label)
        rows.append(row)
    counts = {a: sum(1 for r in rows if r["action"] == a) for a in ("INSTALL", "REPLACE", "SPARE")}
    return {"template": template["code"], "name": template["name"], "verified": template["verified"],
            "source": template["source"], "bike_id": bike.id if bike else None,
            "bike_name": bike.name if bike else None, "options": chosen, "occupied": occupied,
            "items": rows, "counts": counts,
            "new_products": len({(r["type"], r["model"].lower()) for r in rows if not r["product_exists"]})}


def import_groupset(session: Session, code: str, *, at: str, work_session_id: int, bike_id: int | None = None,
                    options: dict | None = None, include: list[str] | None = None,
                    label_prefix: str | None = None, occupied: str = "KEEP", prior_usage: str = "NEW",
                    purchase_date: str | None = None, outcomes: dict[str, str] | None = None,
                    prices: dict[str, int] | None = None, notes: str | None = None) -> dict:
    """Create the parts from ``plan`` and put them in place, all inside one work session.
    ``outcomes`` overrides, per item key, what happens to a replaced part (default per part type).
    ``prices`` are the prices paid per item key (cents); they count as running cost of the bike."""
    p = plan(session, code, bike_id=bike_id, options=options, include=include, label_prefix=label_prefix,
             occupied=occupied)
    template = get_template(code)
    outcomes = outcomes or {}
    prices = prices or {}
    selected = {r["key"] for r in p["items"]}
    for key, cents in prices.items():
        if key not in selected:
            raise DomainError(f"Price given for {key!r}, which is not part of this import")
        if cents is not None and cents < 0:
            raise DomainError("A price cannot be negative")
    for key, outcome in outcomes.items():
        if outcome not in DISPOSITIONS or outcome == "VOIDED":
            raise DomainError(f"{key}: unknown outcome {outcome!r}")
    created: dict[str, Component] = {}
    note = f"Added with the groupset import: {template['name']}" + (f"\n{notes}" if notes else "")
    for row in p["items"]:
        product = session.get(Product, row["product_id"]) if row["product_id"] else None
        if product is None:
            product = _find_product(session, template["maker"], row["model"], row["type"]) or inv.create_product(
                session, component_type=row["type"], maker=template["maker"], model=row["model"],
                specs=row["specs"], spec_source=template["source"],
                spec_version=f"groupset template {template['code']}, {template.get('checked_on') or ''}".strip(", "),
                notes=None if template["verified"] else
                "Specs from the groupset template, not verified against the maker's documentation")
            row["product_id"] = product.id
        comp = inv.create_component(session, component_type=row["type"], label=row["label"], product_id=product.id,
                                    prior_usage=prior_usage, purchase_date=purchase_date or at[:10], notes=note,
                                    price_cents=prices.get(row["key"]),
                                    work_session_id=work_session_id)
        created[row["key"]] = comp
        row["component_id"] = comp.id
        if row["action"] == "INSTALL":
            parent_id = created[row["parent_key"]].id if row["parent_key"] else row["parent_component_id"]
            inv.install(session, comp.id, at=at, bike_id=row["bike_id"] if parent_id is None else None,
                        parent_component_id=parent_id, slot=row["slot"], reallocate=False,
                        work_session_id=work_session_id)
        elif row["action"] == "REPLACE":
            outcome = outcomes.get(row["key"], row["old_outcome"])
            inv.replace(session, row["replaces_component_id"], at=at, new_component_id=comp.id,
                        old_outcome=outcome, reason=f"replaced by {template['series']} groupset",
                        work_session_id=work_session_id)
            row["old_outcome"] = outcome
    inv._reallocate(session)
    return {**p, "work_session_id": work_session_id,
            "created": [{"key": k, "component_id": c.id, "label": c.label} for k, c in created.items()]}


def check_templates() -> list[str]:
    """Problems in the shipped templates (used by tests, so a new template cannot break imports)."""
    problems = []
    for code, t in TEMPLATES.items():
        keys = [i["key"] for i in t["items"]]
        if len(keys) != len(set(keys)):
            problems.append(f"{code}: duplicate item keys")
        option_keys = {o["key"] for o in t["options"]}
        for o in t["options"]:
            if o["default"] not in {c["value"] for c in o["choices"]}:
                problems.append(f"{code}: option {o['key']} default is not a choice")
        for opt_values in _all_choice_sets(t):
            chosen, variables = choose(t, opt_values)
            try:
                resolved = items(t, chosen, variables)
            except (KeyError, ValueError) as e:
                problems.append(f"{code}: placeholder {e} has no value for {opt_values}")
                continue
            for i in resolved:
                ctype = COMPONENT_TYPES.get(i["type"])
                if not ctype:
                    problems.append(f"{code}/{i['key']}: unknown type {i['type']}")
                    continue
                m = i["mount"]
                if ctype.slots and m["slot"] not in ctype.slots:
                    problems.append(f"{code}/{i['key']}: slot {m['slot']} not allowed for {i['type']}")
                if "parent" in m:
                    parent = next((x for x in t["items"] if x["key"] == m["parent"]), None)
                    if not parent or parent["type"] not in ctype.parent_types:
                        problems.append(f"{code}/{i['key']}: cannot be mounted on {m['parent']}")
                if "wheel" in m and m["wheel"] not in ctype.parent_types:
                    problems.append(f"{code}/{i['key']}: cannot be mounted on a {m['wheel']}")
        for i in t["items"]:
            if set((i.get("when") or {})) - option_keys:
                problems.append(f"{code}/{i['key']}: 'when' names an unknown option")
    return problems


def _all_choice_sets(t: dict):
    sets = [{}]
    for o in t["options"]:
        sets = [{**s, o["key"]: c["value"]} for s in sets for c in o["choices"]]
    return sets

