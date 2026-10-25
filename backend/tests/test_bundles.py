"""Purchase bundles: a groupset bought as one bundle at one price; parts kept as spares; later
replacements priced on their own; money counted once."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bikelog.changelog import entries
from bikelog.services import bundles as bsvc
from bikelog.services import costs
from bikelog.services import groupsets as gs
from bikelog.services import inventory as inv
from bikelog.services import worksessions as ws_svc
from bikelog.services.errors import DomainError

from helpers import bike, part

R8100 = "SHIMANO_ULTEGRA_DI2_R8100"


def run_import(session, b, **kw):
    ws = ws_svc.begin(session, at="2026-10-25", bike_id=b.id, title="Groupset")
    return gs.import_groupset(session, R8100, bike_id=b.id, at="2026-10-25", work_session_id=ws.id, **kw), ws


def bundle_import(session, b, **kw):
    return run_import(session, b, to_spares=["bottom_bracket"],
                      bundle={"price_cents": 189900, "merchant": "bike-components.de", "purchased_on": "2026-10-01"},
                      **kw)


def test_groupset_bought_as_one_bundle_with_bottom_bracket_kept_as_spare(session):
    b = bike(session)
    res, _ = bundle_import(session, b)
    rows = {r["key"]: r for r in res["items"]}
    assert rows["bottom_bracket"]["action"] == "SPARE" and rows["bottom_bracket"]["kept_as_spare"]
    assert rows["crankset"]["action"] == "INSTALL"
    bb = inv.get_component(session, rows["bottom_bracket"]["component_id"])
    assert inv.location(session, bb)["state"] == "STORED"
    bundle = bsvc.get(session, res["bundle"]["id"])
    row = bsvc.row(session, bundle)
    installed = sum(1 for r in rows.values() if r["action"] != "SPARE")
    assert row["member_count"] == len(rows) and row["in_use"] == installed
    assert row["merchant"] == "bike-components.de" and row["bike"] == "TIME NXR"
    assert bb.bundle_id == bundle.id and bb.price_cents is None          # the spare stays linked to the bundle
    # shares are an estimate that adds up exactly to the bundle price
    assert sum(m["share_cents"] for m in row["members"]) == 189900
    c = costs.bike_costs(session, b)
    assert c["bundles_cents"] == 189900 and c["running_cents"] == 189900 and c["parts_cents"] == 0
    assert c["unpriced_parts"] == 0
    assert [i for i in c["items"] if i["kind"] == "BUNDLE"][0]["text"].startswith("Shimano Ultegra Di2 R8100")


def test_replaced_parts_get_own_price_and_original_stays_in_the_bundle(session):
    b = bike(session)
    res, _ = bundle_import(session, b)
    pads = {r["key"]: r for r in res["items"]}["pads_front"]["component_id"]
    new = part(session, "BRAKE_PADS", "Front pads 2", price_cents=2499)
    inv.replace(session, pads, at="2026-12-01", new_component_id=new.id, old_outcome="DISCARDED")
    c = costs.bike_costs(session, b)
    assert c["bundles_cents"] == 189900 and c["parts_cents"] == 2499 and c["running_cents"] == 192399
    row = bsvc.row(session, bsvc.get(session, res["bundle"]["id"]))
    old = next(m for m in row["members"] if m["component_id"] == pads)
    installed = sum(1 for r in res["items"] if r["action"] != "SPARE")
    assert not old["in_use"] and row["in_use"] == installed - 1             # the discarded pads
    assert new.bundle_id is None


def test_no_double_counting_rules(session):
    b = bike(session)
    res, _ = bundle_import(session, b)
    chain = {r["key"]: r for r in res["items"]}["chain"]["component_id"]
    with pytest.raises(DomainError, match="bundle"):
        inv.update_component(session, chain, price_cents=4000)
    priced = part(session, "CHAIN", "Chain X", price_cents=3999)
    with pytest.raises(DomainError, match="own price"):
        bsvc.add_members(session, res["bundle"]["id"], [priced.id])
    with pytest.raises(DomainError, match="either one price"):
        run_import(session, bike(session, "BMC Roadmachine"), prices={"chain": 100}, bundle={"price_cents": 5})


def test_bundle_from_existing_parts_edit_void_and_undo(session):
    b = bike(session)
    res, ws = run_import(session, b)          # imported earlier without a bundle
    ids = [r["component_id"] for r in res["items"]]
    bundle = bsvc.create(session, name="Ultegra groupset", component_ids=ids, merchant="Shop",
                         purchased_on="2026-09-30", price_cents=150000)
    assert costs.bike_costs(session, b)["running_cents"] == 150000
    bsvc.update(session, bundle.id, price_cents=160000)
    assert costs.bike_costs(session, b)["running_cents"] == 160000
    session.flush()
    log = entries(session, component_id=ids[0])
    assert any(r["field"] == "bought in bundle" and r["new_value"] == "Ultegra groupset" for r in log)
    bsvc.void(session, bundle.id, "entered twice")
    assert costs.bike_costs(session, b)["running_cents"] == 0
    inv.update_component(session, ids[0], price_cents=1000)     # free again once the bundle is voided
    session.commit()
    with pytest.raises(IntegrityError, match="PROTECTED"):
        session.execute(text("DELETE FROM purchase_bundle"))
    session.rollback()
    # undoing the groupset import also voids a bundle made by that import
    b2 = bike(session, "BMC Roadmachine")
    res2, ws2 = bundle_import(session, b2)
    ws_svc.undo(session, ws2.id, reason="test")
    assert bsvc.get(session, res2["bundle"]["id"]).voided_at is not None
    assert costs.bike_costs(session, b2)["running_cents"] == 0
