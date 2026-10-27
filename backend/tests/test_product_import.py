"""JSON product import: templates, validation with clear errors, idempotent re-import, items, CLI."""
import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bikelog import launcher
from bikelog.api.app import create_app
from bikelog.catalog import COMPONENT_TYPES
from bikelog.db import make_session_factory, session_scope
from bikelog.models import Component, Product
from bikelog.product_specs import SPEC_FIELDS
from bikelog.services import product_import as pi
from bikelog.services.reference import ensure_reference_data

DOCS = Path(__file__).resolve().parents[2] / "docs" / "product-templates"


def chain(**kw):
    doc = {"format": "bikelog.product.v1", "component_type": "CHAIN", "maker": "Shimano", "model": "CN-M8100",
           "list_price": 39.95, "specs": {"speeds": 12, "links": 116},
           "source": {"url": "https://shop.example/cn-m8100", "retrieved_at": "2026-10-25", "tool": "scraper 0.1"}}
    doc.update(kw)
    return doc


def test_every_type_has_a_template_and_examples_match_schemas():
    assert set(SPEC_FIELDS) == set(COMPONENT_TYPES)
    for code in COMPONENT_TYPES:
        s = pi.schema(code)
        jsonschema.Draft202012Validator.check_schema(s)
        jsonschema.validate(pi.example(code), s)
        assert pi.validate(pi.example(code))["errors"] == []


def test_shipped_template_files_are_up_to_date():
    for code in COMPONENT_TYPES:
        for kind, fn in (("schema", pi.schema), ("example", pi.example)):
            f = DOCS / f"{code.lower()}.{kind}.json"
            assert json.loads(f.read_text(encoding="utf-8")) == fn(code), \
                f"{f.name} is stale: run python -m bikelog --write-product-templates docs/product-templates"
    assert (DOCS / "AGENT_INSTRUCTIONS.md").read_text(encoding="utf-8") == pi.agent_instructions()


def test_import_is_idempotent_and_updates_changed_products(session):
    r = pi.import_products(session, chain(items=[{"label": "Chain C", "price": 35.5, "purchase_date": "2026-10-20"}]))
    assert r["ok"] and r["counts"]["CREATED"] == 1 and r["counts"]["ITEMS_CREATED"] == 1
    p = session.scalar(select(Product).where(Product.model == "CN-M8100"))
    assert p.list_price_cents == 3995 and "unverified" in p.spec_version and p.spec_source.startswith("https://")
    c = session.scalar(select(Component).where(Component.label == "Chain C"))
    assert c.product_id == p.id and c.price_cents == 3550 and c.disposition == "STORED"
    again = pi.import_products(session, chain(items=[{"label": "chain c"}]))
    assert again["counts"] == {"CREATED": 0, "UPDATED": 0, "UNCHANGED": 1, "ITEMS_CREATED": 0, "ITEMS_EXISTING": 1}
    # app-side spec kept, file values win
    p.specs_json = json.dumps({"speeds": 12, "links": 116, "my_note": "waxed"})
    upd = pi.import_products(session, chain(model="cn-m8100", specs={"speeds": 12, "links": 126}))
    assert upd["products"][0]["status"] == "UPDATED" and upd["products"][0]["changed"] == ["links"]
    assert json.loads(p.specs_json) == {"speeds": 12, "links": 126, "my_note": "waxed"}
    assert session.scalar(select(func.count(Product.id))) == 1


def test_validation_lists_every_error_and_writes_nothing(session):
    bad = {"format": "bikelog.products.v1", "products": [
        chain(specs={"speeds": "twelve", "links": 116.5}),
        {"component_type": "SPROCKET", "maker": "X", "model": "Y"},
        chain(model="Other", currency="USD", items=[{"label": ""}], colour="black"),
        chain(),
        chain(),
    ]}
    r = pi.import_products(session, bad)
    assert not r["ok"]
    text = "\n".join(r["errors"])
    for expected in ("products[0].specs.speeds: expected a number", "products[0].specs.links: expected a whole number",
                     "products[1].component_type: 'SPROCKET'", "products[2].currency: only EUR",
                     "products[2].items[0].label", "products[2]: unknown fields colour",
                     "products[4]: same product as products[3]"):
        assert expected in text, expected
    assert session.scalar(select(func.count(Product.id))) == 0


def test_friendly_coercion_and_extra_spec_fields(session):
    r = pi.import_products(session, chain(specs={"speeds": "12", "weight_g": "257,5", "coating": "nickel"},
                                          verified=True))
    assert r["ok"]
    assert any("read as a number" in w for w in r["warnings"])
    assert any("coating" in w for w in r["warnings"])
    p = session.scalar(select(Product))
    assert json.loads(p.specs_json) == {"speeds": 12, "weight_g": 257.5, "coating": "nickel"}
    assert p.spec_version.endswith("; verified")


def test_dry_run_and_list_files(session):
    r = pi.import_products(session, [chain(), chain(model="CN-R9100", items=[{"label": "Spare 11s"}])], dry_run=True)
    assert r["ok"] and r["counts"]["CREATED"] == 2 and r["counts"]["ITEMS_CREATED"] == 1
    assert session.scalar(select(func.count(Product.id))) == 0
    with pytest.raises(Exception, match="line 1"):
        pi.parse(b"{not json")


def test_http_and_command_line(engine, paths, tmp_path, capsys):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
    c = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    c.headers.update({"X-BikeLog-Token": "t"})
    assert len(c.get("/api/product-templates").json()) == len(COMPONENT_TYPES)
    assert c.get("/api/product-templates/CASSETTE/schema").json()["properties"]["component_type"]["const"] == "CASSETTE"
    body = json.dumps(chain()).encode()
    assert c.post("/api/imports/products?dry_run=true", content=body).json()["counts"]["CREATED"] == 1
    assert c.post("/api/imports/products", content=body).json()["counts"]["CREATED"] == 1
    assert c.post("/api/imports/products", content=b"[").status_code == 400
    engine.dispose()
    f = tmp_path / "rotor.json"
    f.write_text(json.dumps(pi.example("BRAKE_ROTOR")), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"component_type": "CHAIN"}), encoding="utf-8")
    code = launcher.main(["--data-dir", str(paths.root), "--import-products", str(f), str(bad)])
    out = capsys.readouterr()
    assert code == 1
    assert "1 new" in out.out and "file.maker: required text" in out.err
