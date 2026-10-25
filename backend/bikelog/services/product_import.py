"""JSON import of products (and optional spare items) produced by external scripts, e.g. scrapers.

One template per component type (``schema`` + ``example``). A file holds one product, a list of
products, or {"format": "bikelog.products.v1", "products": [...]}. Import rules:
- the whole file is validated first; with any error nothing is written and every error is listed
  with its path (e.g. ``products[2].specs.speeds``)
- a product is identified by component type + maker + model (case-insensitive): importing the same file
  again changes nothing, a changed file updates that product (specs are merged: keys in the file win,
  keys only in the app are kept)
- items are physical parts (stored as spares) identified by their label; an existing label is left alone
- scraped data is marked unverified unless the file says ``"verified": true``
"""
from __future__ import annotations

import json
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.catalog import COMPONENT_TYPES
from bikelog.models import Component, Product
from bikelog.product_specs import SpecField, fields_for
from bikelog.services import inventory as inv
from bikelog.services.errors import DomainError

FORMAT = "bikelog.product.v1"
LIST_FORMAT = "bikelog.products.v1"
TOP_KEYS = {"format", "component_type", "maker", "model", "list_price", "currency", "specs", "source", "verified",
            "notes", "items"}
ITEM_KEYS = {"label", "price", "purchase_date", "prior_usage", "serial_number", "storage_location", "notes"}
SOURCE_KEYS = {"url", "retrieved_at", "tool"}
MAX_PRODUCTS = 2000
_KIND_TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean", "enum": "string"}


# ------------------------------------------------------------------ templates

def schema(component_type: str) -> dict:
    """JSON Schema (draft 2020-12) of one product file for this component type."""
    ctype = _ctype(component_type)
    spec_props = {}
    for f in fields_for(component_type):
        prop: dict = {"type": _KIND_TYPES[f.kind], "description": f.description + (f" ({f.unit})" if f.unit else "")}
        if f.values:
            prop["enum"] = list(f.values)
        spec_props[f.key] = prop
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"bikelog/product-templates/{component_type.lower()}.schema.json",
        "title": f"Bike Log product: {ctype.name}",
        "description": "One product (what you can buy) and optionally physical items you own. Only "
                       "component_type, maker and model are required. Unlisted spec keys are imported too.",
        "type": "object",
        "required": ["component_type", "maker", "model"],
        "additionalProperties": False,
        "properties": {
            "format": {"const": FORMAT},
            "component_type": {"const": component_type},
            "maker": {"type": "string", "minLength": 1},
            "model": {"type": "string", "minLength": 1, "description": "Model name or number, unique per maker"},
            "list_price": {"type": "number", "minimum": 0, "description": "Reference price in euro (not money spent)"},
            "currency": {"const": "EUR"},
            "specs": {"type": "object", "properties": spec_props, "additionalProperties": True},
            "source": {"type": "object", "additionalProperties": False, "properties": {
                "url": {"type": "string"}, "retrieved_at": {"type": "string", "format": "date"},
                "tool": {"type": "string", "description": "Script name and version"}}},
            "verified": {"type": "boolean", "description": "true only if checked against the maker's documentation"},
            "notes": {"type": "string"},
            "items": {"type": "array", "description": "Physical parts you own of this product (added as spares)",
                      "items": {"type": "object", "required": ["label"], "additionalProperties": False, "properties": {
                          "label": {"type": "string", "minLength": 1},
                          "price": {"type": "number", "minimum": 0, "description": "Price paid in euro"},
                          "purchase_date": {"type": "string", "format": "date"},
                          "prior_usage": {"enum": ["NEW", "UNKNOWN"]},
                          "serial_number": {"type": "string"},
                          "storage_location": {"type": "string"},
                          "notes": {"type": "string"}}}},
        },
    }


def example(component_type: str) -> dict:
    ctype = _ctype(component_type)
    specs = {f.key: f.example for f in fields_for(component_type) if f.example is not None}
    return {
        "format": FORMAT,
        "component_type": component_type,
        "maker": "Example maker",
        "model": f"Example {ctype.name.lower()} 1",
        "list_price": 49.9,
        "currency": "EUR",
        "specs": specs,
        "source": {"url": "https://example.com/product-page", "retrieved_at": "2026-10-25", "tool": "my-scraper 1.0"},
        "verified": False,
        "notes": "Optional free text",
        "items": [{"label": f"Spare {ctype.name.lower()} 1", "price": 44.9, "purchase_date": "2026-10-20",
                   "prior_usage": "NEW", "storage_location": "Workshop drawer"}],
    }


def templates() -> list[dict]:
    return [{"component_type": c, "name": t.name, "category": t.category,
             "spec_fields": [{"key": f.key, "kind": f.kind, "description": f.description, "unit": f.unit,
                              "values": list(f.values)} for f in fields_for(c)]}
            for c, t in COMPONENT_TYPES.items()]


def _ctype(code: str):
    t = COMPONENT_TYPES.get(code)
    if not t:
        raise DomainError(f"Unknown component type {code!r}")
    return t


# ------------------------------------------------------------------ validation

def _products(doc) -> list:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and "products" in doc:
        if doc.get("format", LIST_FORMAT) != LIST_FORMAT:
            raise DomainError(f"Unsupported format {doc.get('format')!r}; expected {LIST_FORMAT!r}")
        if not isinstance(doc["products"], list):
            raise DomainError("'products' must be a list")
        return doc["products"]
    if isinstance(doc, dict):
        return [doc]
    raise DomainError("The file must contain a JSON object or a list of objects")


def _is_date(v) -> bool:
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _coerce(f: SpecField, v, where: str, errors: list, warnings: list):
    """Scrapers often give numbers as text ("1,8 mm" is not accepted, "1,8" is)."""
    if v is None:
        return None
    if f.kind in ("number", "integer"):
        if isinstance(v, bool):
            errors.append(f"{where}: expected a number, got true/false")
            return None
        if isinstance(v, str):
            try:
                v2 = float(v.strip().replace(",", "."))
            except ValueError:
                errors.append(f"{where}: expected a number{f' in {f.unit}' if f.unit else ''}, got {v!r}")
                return None
            warnings.append(f"{where}: text {v!r} read as a number")
            v = v2
        if not isinstance(v, (int, float)):
            errors.append(f"{where}: expected a number, got {type(v).__name__}")
            return None
        if f.kind == "integer":
            if float(v) != int(v):
                errors.append(f"{where}: expected a whole number, got {v}")
                return None
            return int(v)
        return v if isinstance(v, int) else float(v)
    if f.kind == "boolean":
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "yes", "false", "no"):
            warnings.append(f"{where}: text {v!r} read as true/false")
            return v.strip().lower() in ("true", "yes")
        errors.append(f"{where}: expected true or false, got {v!r}")
        return None
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        errors.append(f"{where}: expected text, got {type(v).__name__}")
        return None
    v = str(v).strip()
    if f.kind == "enum" and v not in f.values:
        match = next((x for x in f.values if x.lower() == v.lower()), None)
        if match is None:
            errors.append(f"{where}: {v!r} is not one of {', '.join(f.values)}")
            return None
        v = match
    return v


def _money(v, where: str, errors: list) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        errors.append(f"{where}: expected an amount in euro such as 49.9")
        return None
    return round(v * 100)


def validate(doc) -> dict:
    """Check a whole file; returns normalised products, errors and warnings. Never writes."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw = _products(doc)
    except DomainError as e:
        return {"products": [], "errors": [str(e)], "warnings": []}
    if len(raw) > MAX_PRODUCTS:
        return {"products": [], "errors": [f"Too many products in one file (max {MAX_PRODUCTS})"], "warnings": []}
    multi = not (isinstance(doc, dict) and "products" not in doc)
    out = []
    seen: dict[tuple, str] = {}
    labels: dict[tuple, str] = {}
    for n, p in enumerate(raw):
        at = f"products[{n}]" if multi else "file"
        before = len(errors)
        if not isinstance(p, dict):
            errors.append(f"{at}: expected an object")
            continue
        unknown = set(p) - TOP_KEYS
        if unknown:
            errors.append(f"{at}: unknown fields {', '.join(sorted(unknown))} (put product data under 'specs')")
        if p.get("format", FORMAT) != FORMAT:
            errors.append(f"{at}.format: expected {FORMAT!r}")
        ctype = p.get("component_type")
        if ctype not in COMPONENT_TYPES:
            errors.append(f"{at}.component_type: {ctype!r} is not a Bike Log part type "
                          f"(one of {', '.join(COMPONENT_TYPES)})")
        maker = p.get("maker")
        model = p.get("model")
        for key, val in (("maker", maker), ("model", model)):
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{at}.{key}: required text")
        if p.get("currency", "EUR") != "EUR":
            errors.append(f"{at}.currency: only EUR is supported; convert prices before importing")
        list_price = _money(p.get("list_price"), f"{at}.list_price", errors)
        specs_in = p.get("specs") or {}
        specs: dict = {}
        if not isinstance(specs_in, dict):
            errors.append(f"{at}.specs: expected an object")
            specs_in = {}
        known = {f.key: f for f in fields_for(ctype)} if ctype in COMPONENT_TYPES else {}
        extra = []
        for k, v in specs_in.items():
            if k in known:
                val = _coerce(known[k], v, f"{at}.specs.{k}", errors, warnings)
                if val is not None:
                    specs[k] = val
            elif isinstance(v, (str, int, float, bool)) or v is None:
                extra.append(k)
                if v is not None:
                    specs[k] = v
            else:
                errors.append(f"{at}.specs.{k}: values must be text, numbers or true/false")
        if extra:
            warnings.append(f"{at}.specs: kept fields not in the template: {', '.join(extra)}")
        source = p.get("source") or {}
        if not isinstance(source, dict):
            errors.append(f"{at}.source: expected an object")
            source = {}
        if set(source) - SOURCE_KEYS:
            errors.append(f"{at}.source: unknown fields {', '.join(sorted(set(source) - SOURCE_KEYS))}")
        if source.get("retrieved_at") is not None and not _is_date(source.get("retrieved_at")):
            errors.append(f"{at}.source.retrieved_at: expected a date like 2026-10-25")
        verified = p.get("verified", False)
        if not isinstance(verified, bool):
            errors.append(f"{at}.verified: expected true or false")
        items = []
        for i, it in enumerate(p.get("items") or []):
            iat = f"{at}.items[{i}]"
            if not isinstance(it, dict):
                errors.append(f"{iat}: expected an object")
                continue
            if set(it) - ITEM_KEYS:
                errors.append(f"{iat}: unknown fields {', '.join(sorted(set(it) - ITEM_KEYS))}")
            label = it.get("label")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"{iat}.label: required text, e.g. 'Spare chain 1'")
                continue
            key = (ctype, label.strip().lower())
            if key in labels:
                errors.append(f"{iat}.label: {label!r} is used twice in this file (also {labels[key]})")
            labels[key] = iat
            if it.get("purchase_date") is not None and not _is_date(it["purchase_date"]):
                errors.append(f"{iat}.purchase_date: expected a date like 2026-10-25")
            if it.get("prior_usage", "NEW") not in ("NEW", "UNKNOWN"):
                errors.append(f"{iat}.prior_usage: NEW or UNKNOWN")
            items.append({"label": label.strip(), "price_cents": _money(it.get("price"), f"{iat}.price", errors),
                          "purchase_date": it.get("purchase_date"), "prior_usage": it.get("prior_usage", "NEW"),
                          "serial_number": it.get("serial_number"), "storage_location": it.get("storage_location"),
                          "notes": it.get("notes")})
        if isinstance(p.get("items"), (str, dict)):
            errors.append(f"{at}.items: expected a list")
        if len(errors) > before:
            continue
        ident = (ctype, maker.strip().lower(), model.strip().lower())
        if ident in seen:
            errors.append(f"{at}: same product as {seen[ident]} ({maker} {model})")
            continue
        seen[ident] = at
        out.append({"at": at, "component_type": ctype, "maker": maker.strip(), "model": model.strip(),
                    "list_price_cents": list_price, "specs": specs, "source": source, "verified": verified,
                    "notes": p.get("notes"), "items": items})
    return {"products": out, "errors": errors, "warnings": warnings}


# ------------------------------------------------------------------ import

def _spec_version(p: dict) -> str:
    src = p["source"]
    when = src.get("retrieved_at") or date.today().isoformat()
    tool = f" by {src['tool']}" if src.get("tool") else ""
    return f"JSON import {when}{tool}; {'verified' if p['verified'] else 'unverified'}"


def import_products(session: Session, doc, *, dry_run: bool = False) -> dict:
    """Validate, then create or update products and add items. With errors, nothing is written."""
    v = validate(doc)
    report = {"ok": not v["errors"], "errors": v["errors"], "warnings": v["warnings"], "dry_run": dry_run,
              "products": [], "counts": {"CREATED": 0, "UPDATED": 0, "UNCHANGED": 0, "ITEMS_CREATED": 0,
                                         "ITEMS_EXISTING": 0}}
    if v["errors"]:
        return report
    for p in v["products"]:
        prod = session.scalar(select(Product).where(
            Product.component_type == p["component_type"], func.lower(Product.maker) == p["maker"].lower(),
            func.lower(Product.model) == p["model"].lower()).order_by(Product.id))
        row = {"at": p["at"], "component_type": p["component_type"], "maker": p["maker"], "model": p["model"],
               "changed": [], "items": []}
        spec_source = p["source"].get("url") or "JSON import"
        if prod is None:
            row["status"] = "CREATED"
            if not dry_run:
                prod = inv.create_product(session, component_type=p["component_type"], maker=p["maker"],
                                          model=p["model"], specs=p["specs"], spec_source=spec_source,
                                          spec_version=_spec_version(p), notes=p["notes"],
                                          list_price_cents=p["list_price_cents"])
        else:
            old_specs = json.loads(prod.specs_json or "{}")
            merged = {**old_specs, **p["specs"]}
            changed = sorted(k for k in merged if old_specs.get(k) != merged.get(k))
            updates = {}
            if changed:
                updates["specs"] = merged
            if p["list_price_cents"] is not None and p["list_price_cents"] != prod.list_price_cents:
                updates["list_price_cents"] = p["list_price_cents"]
                changed.append("list_price")
            if p["notes"] is not None and p["notes"] != prod.notes:
                updates["notes"] = p["notes"]
                changed.append("notes")
            if p["source"].get("url") and p["source"]["url"] != prod.spec_source:
                updates["spec_source"] = spec_source
                changed.append("source")
            if updates:
                updates["spec_version"] = _spec_version(p)
            row["status"] = "UPDATED" if updates else "UNCHANGED"
            row["changed"] = changed
            if updates and not dry_run:
                inv.update_product(session, prod.id, **updates)
        report["counts"][row["status"]] += 1
        for it in p["items"]:
            existing = session.scalar(select(Component).where(
                Component.component_type == p["component_type"], func.lower(Component.label) == it["label"].lower()))
            if existing is not None:
                if prod is not None and existing.product_id not in (None, prod.id):
                    raise DomainError(f"{p['at']}: a part labelled {it['label']!r} already exists for another "
                                      "product; choose a different label")
                row["items"].append({"label": it["label"], "status": "EXISTS", "component_id": existing.id})
                report["counts"]["ITEMS_EXISTING"] += 1
                continue
            cid = None
            if not dry_run:
                comp = inv.create_component(session, component_type=p["component_type"], label=it["label"],
                                            product_id=prod.id, prior_usage=it["prior_usage"],
                                            price_cents=it["price_cents"], purchase_date=it["purchase_date"],
                                            serial_number=it["serial_number"], notes=it["notes"],
                                            storage_location=it["storage_location"])
                cid = comp.id
            row["items"].append({"label": it["label"], "status": "CREATED", "component_id": cid})
            report["counts"]["ITEMS_CREATED"] += 1
        if prod is not None:
            row["product_id"] = prod.id
        report["products"].append(row)
    return report


def parse(content: bytes | str) -> object:
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise DomainError("The file is not UTF-8 text") from e
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise DomainError(f"Not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}") from e


def run_import(factory, content: bytes | str, *, dry_run: bool = False) -> dict:
    """Parse and import one file in its own transaction (rolled back on any error)."""
    from bikelog.db import session_scope
    doc = parse(content)
    with session_scope(factory) as s:
        return import_products(s, doc, dry_run=dry_run)


def agent_instructions() -> str:
    """Self-contained instructions for a person or an AI agent writing a script (e.g. a scraper) that
    produces import files. Generated from the templates so it never disagrees with the importer."""
    from bikelog.product_specs import COMMON
    types = "\n".join(f"| `{c}` | {t.name} | {t.category} |" for c, t in COMPONENT_TYPES.items())
    common = ", ".join(f"`{f.key}`" for f in COMMON)
    sections = []
    for code, t in COMPONENT_TYPES.items():
        rows = []
        for f in fields_for(code):
            kind = "one of " + ", ".join(f"`{v}`" for v in f.values) if f.values else f.kind
            rows.append(f"| `{f.key}` | {kind} | {f.unit or ''} | {f.description} |")
        sections.append(f"### {t.name} (`{code}`)\n\nTemplate: `{code.lower()}.schema.json`, example: "
                        f"`{code.lower()}.example.json`\n\n| key | type | unit | meaning |\n|---|---|---|---|\n"
                        + "\n".join(rows))
    ex = json.dumps(example("CASSETTE"), indent=2, ensure_ascii=False)
    return f"""# Instructions: write a script that creates Bike Log product files

This document is self-contained. Give it to a developer or an AI coding agent together with the task,
for example: "Write a Python script that reads the product pages I give it and writes Bike Log import
files following these instructions."

Generated by Bike Log from its import templates (format `{FORMAT}`). Do not edit by hand; run
`BikeLog.exe --write-product-templates <folder>` to regenerate it with the JSON schemas.

## What Bike Log does with the files

Bike Log is a local app that tracks bike parts. It imports **products** (a model you can buy, such as a
Shimano CN-M8100 chain) with their specs, and optionally **items** (physical parts the user owns, added
as spares). Import is safe to repeat: the same file twice changes nothing; a changed file updates the
product. A file with any error is rejected as a whole and every error is listed.

## Output files

- UTF-8 JSON, one product per file (recommended) or several in one file:
  `{{"format": "{LIST_FORMAT}", "products": [ ... ]}}` (a plain JSON list also works).
- File name (recommended): `<component_type in lower case>--<maker>-<model>.json`, using only
  `a-z 0-9 - .`, for example `cassette--shimano-cs-r8100-12-11-34.json`.
- At most {MAX_PRODUCTS} products per file and 5 MB per file.

## Fields of one product

| field | required | type | rules |
|---|---|---|---|
| `format` | recommended | text | always `"{FORMAT}"` |
| `component_type` | yes | text | exactly one code from the table below |
| `maker` | yes | text | brand as printed by the maker, e.g. `"Shimano"` |
| `model` | yes | text | model name/number **including the variant that changes what you buy**: size, length, teeth, range. E.g. `"CS-R8100-12 11-34"`, `"RT-CL800 160 mm"`, `"GP5000 S TR 700x28c"` |
| `list_price` | no | number | reference price in **euro**, decimal point, no currency sign, e.g. `69.95` |
| `currency` | no | text | only `"EUR"`; convert other currencies before writing, or leave the price out |
| `specs` | no | object | spec fields of that type (tables below); see rules |
| `source` | strongly recommended | object | `url` (product page), `retrieved_at` (date `YYYY-MM-DD`), `tool` (script name and version) |
| `verified` | no | true/false | always `false` for scraped data; only a person checking the maker's documentation sets `true` |
| `notes` | no | text | anything that does not fit a spec field |
| `items` | no | list | only for parts the user actually owns; a scraper normally leaves this out |

Item fields: `label` (required, unique name such as `"Spare chain 2"`), `price` (euro paid),
`purchase_date` (`YYYY-MM-DD`), `prior_usage` (`"NEW"` or `"UNKNOWN"`), `serial_number`,
`storage_location`, `notes`.

Product identity is `component_type + maker + model` (case-insensitive). Keep `maker` and `model`
spelled the same on every run, otherwise a second product is created. Any other top-level field is an
error; put extra data under `specs`.

## Rules for specs

1. **Never guess.** Leave a field out when the page does not state it. Missing is fine; wrong is not.
2. **Use the units in the tables** and write plain JSON numbers: `"diameter_mm": 160`, not `"160mm"`.
   Convert inches to mm (× 25.4) and pounds to grams (× 453.6) before writing.
3. Whole numbers for `integer` fields (`speeds`, `teeth`, `links`). Decimal point, not comma.
4. `true` / `false` for yes/no fields, without quotes.
5. For "one of" fields use exactly one of the listed values.
6. Spec keys that are not in the table are allowed (text, number or true/false only) and are kept; the
   import reports them as warnings. Use lower_snake_case keys with a unit suffix, e.g. `stack_mm`.
7. Bike Log reads `"12"` or `"1,5"` as numbers but warns; better to write real numbers.

## Part types

| code | name | group |
|---|---|---|
{types}

Every type also accepts {common}.

## Spec fields per type

{chr(10).join(sections)}

## Check and import

- In the app: Inventory → **Import JSON** → choose files → **Check files** (shows every error and what
  would change) → **Import**.
- From the command line (Bike Log must be closed; a backup is written first):
  `BikeLog.exe --import-products file1.json file2.json` and `--dry-run` to only check.
  Exit code 0 = all files fine, 1 = at least one file had errors (that file was not imported).
- Error messages name the place, e.g. `products[2].specs.speeds: expected a whole number, got 11.5`.
- The script can validate before writing with the JSON schemas in this folder
  (`<type>.schema.json`, JSON Schema draft 2020-12; Python: `jsonschema.validate(doc, schema)`).

## Being a good citizen

Fetch only pages the user asks for, respect the site's robots.txt and terms, wait at least one second
between requests, send an honest User-Agent, never log in or bypass paywalls or bot protection, and keep
the data for the user's own use.

## Complete example

```json
{ex}
```
"""
