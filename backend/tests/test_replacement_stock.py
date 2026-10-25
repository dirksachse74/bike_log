"""Replacement workflow, spare-parts stock, tracking modes and work-session undo (Dirk's examples)."""
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from bikelog.models import Component, ComponentDisposition
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import stock
from bikelog.services import worksessions as ws_svc
from bikelog.services.errors import Conflict, DomainError

from helpers import bike, km, part, ride


def wheels(session, b):
    front = part(session, "FRONT_WHEEL", "Front wheel")
    rear = part(session, "REAR_WHEEL", "Rear wheel")
    inv.install(session, front.id, bike_id=b.id, at="2026-08-01")
    inv.install(session, rear.id, bike_id=b.id, at="2026-08-01")
    return front, rear


def test_punctured_rear_tube_replaced_old_awaiting_repair_then_patched_back_to_spares(session):
    b = bike(session)
    _, rear = wheels(session, b)
    old = part(session, "INNER_TUBE", "Rear tube")          # no serial number or specs needed
    inv.install(session, old.id, parent_component_id=rear.id, at="2026-08-01")
    ride(session, b, "2026-08-10", 120)
    patches = stock.add_consumable(session, name="Park GP-2 patches", tracking_mode="COUNTED", unit="patch")
    stock.consumable_txn(session, patches.id, kind="PURCHASE", qty=6, packages=1, on="2026-08-01", cost_cents=450)

    ws = ws_svc.begin(session, at="2026-08-12", bike_id=b.id, title="Puncture")
    res = inv.replace(session, old.id, at="2026-08-12", reason="puncture", new={"label": "Spare tube 1"},
                      work_session_id=ws.id)
    assert res["old_outcome"] == "AWAITING_SERVICE"          # suggested default for a tube
    ride(session, b, "2026-08-14", 50)
    assert km(session, old) == 120 and km(session, inv.get_component(session, res["new_component_id"])) == 50
    assert inv.location(session, old)["state"] == "AWAITING_SERVICE"
    with pytest.raises(DomainError, match="awaiting"):
        inv.install(session, old.id, parent_component_id=rear.id, at="2026-08-15")

    # Patch the removed tube: repair recorded, one patch used, back in spares, mileage kept
    m.log_event(session, action_code="TUBE_PATCH", component_id=old.id, at="2026-08-15", outcome="REPAIRED",
                consumable_id=patches.id, consumable_qty=1)
    assert inv.location(session, old)["state"] == "STORED"
    assert stock.level(session, patches)["qty"] == 5
    assert km(session, old) == 120
    hist = [d["disposition"] for d in inv.disposition_history(session, old)]
    assert hist == ["AWAITING_SERVICE", "STORED"]


def test_discarded_tube_keeps_its_record_and_history(session):
    b = bike(session)
    _, rear = wheels(session, b)
    old = part(session, "INNER_TUBE", "Rear tube")
    inv.install(session, old.id, parent_component_id=rear.id, at="2026-08-01")
    ride(session, b, "2026-08-10", 80)
    inv.replace(session, old.id, at="2026-08-12", same_product=True, old_outcome="DISCARDED", reason="split valve")
    assert old.status == "RETIRED" and old.disposition == "DISCARDED"
    assert km(session, old) == 80
    assert inv.installation_history(session, old)[0]["removal_outcome"] == "DISCARDED"
    with pytest.raises(IntegrityError):  # the database itself refuses to delete history
        session.execute(text("DELETE FROM component_disposition"))


def test_replace_bar_tape_discards_old_and_records_new_with_product_and_cost(session):
    b = bike(session)
    old = part(session, "BAR_TAPE", "Black tape")
    inv.install(session, old.id, bike_id=b.id, at="2026-01-01")
    ride(session, b, "2026-05-01", 300)
    prod = inv.create_product(session, component_type="BAR_TAPE", maker="Supacaz", model="Super Sticky Kush")
    ws = ws_svc.begin(session, at="2026-06-01", bike_id=b.id)
    res = inv.replace(session, old.id, at="2026-06-01", new={"product_id": prod.id, "price_cents": 3495},
                      work_session_id=ws.id)
    new = inv.get_component(session, res["new_component_id"])
    assert res["old_outcome"] == "DISCARDED"                 # suggested choice for used bar tape
    assert new.product_id == prod.id and new.price_cents == 3495 and new.purchase_date == "2026-06-01"
    assert inv.location(session, new)["since"] == "2026-06-01"
    assert ws_svc.summary(session, ws.id)["cost_cents"] == 3495
    assert km(session, old) == 300 and km(session, new) == 0


def test_rewrap_is_service_on_the_same_tape(session):
    b = bike(session)
    tape = part(session, "BAR_TAPE", "Black tape")
    inv.install(session, tape.id, bike_id=b.id, at="2026-01-01")
    ride(session, b, "2026-05-01", 300)
    before = session.scalar(select(func.count()).select_from(Component))
    m.log_event(session, action_code="BAR_TAPE_REWRAP", component_id=tape.id, at="2026-05-02")
    ride(session, b, "2026-05-03", 40)
    assert session.scalar(select(func.count()).select_from(Component)) == before
    assert km(session, tape) == 340                          # lifetime usage not reset
    assert inv.location(session, tape)["state"] == "INSTALLED"


def test_move_tire_rear_to_front_keeps_identity_and_mileage(session):
    b = bike(session)
    front, rear = wheels(session, b)
    tire_r = part(session, "TIRE", "GP5000 A")
    tire_f = part(session, "TIRE", "GP5000 B")
    inv.install(session, tire_r.id, parent_component_id=rear.id, at="2026-08-01")
    inv.install(session, tire_f.id, parent_component_id=front.id, at="2026-08-01")
    ride(session, b, "2026-08-05", 100)
    with pytest.raises(Conflict):
        inv.move(session, tire_r.id, at="2026-08-06", parent_component_id=front.id)
    inv.move(session, tire_r.id, at="2026-08-06", parent_component_id=front.id, swap=True)
    ride(session, b, "2026-08-08", 30)
    assert km(session, tire_r) == 130 and km(session, tire_f) == 130
    assert inv.location(session, tire_r)["parent_component_id"] == front.id
    assert inv.location(session, tire_f)["parent_component_id"] == rear.id
    hist = inv.installation_history(session, tire_r)
    assert [h["removal_outcome"] for h in hist] == ["MOVED", None]
    assert session.scalar(select(func.count()).select_from(Component).where(Component.label.like("GP5000%"))) == 2


def test_rear_pads_from_stock_three_to_two_old_discarded_and_undo_restores(session):
    b = bike(session)
    old = part(session, "BRAKE_PADS", "Rear pads (fitted)")
    inv.install(session, old.id, bike_id=b.id, slot="REAR_PADS", at="2026-01-01")
    ride(session, b, "2026-03-01", 900)
    prod = inv.create_product(session, component_type="BRAKE_PADS", maker="Shimano", model="L05A-RF")
    line = stock.add_consumable(session, product_id=prod.id, storage_location="Workshop drawer", min_stock=1)
    assert line.unit == "set" and "one caliper" in line.unit_note
    stock.consumable_txn(session, line.id, kind="PURCHASE", qty=3, on="2026-02-01", cost_cents=4500)

    ws = ws_svc.begin(session, at="2026-03-02", bike_id=b.id, title="Rear pads")
    res = inv.replace(session, old.id, at="2026-03-02", from_stock_id=line.id, reason="worn",
                      work_session_id=ws.id)
    new = inv.get_component(session, res["new_component_id"])
    assert stock.level(session, line)["qty"] == 2            # three sets → two
    assert old.disposition == "DISCARDED" and new.product_id == prod.id
    assert new.from_stock_txn_id is not None and new.price_cents is None   # cost stays on the purchase
    row = next(r for r in stock.consumable_stock(session) if r["id"] == line.id)
    assert row["available_total"] == 2                       # the installed set is not also "available"
    assert ws_svc.summary(session, ws.id)["cost_cents"] == 0
    assert inv.location(session, new)["slot"] == "REAR_PADS"

    ws_svc.undo(session, ws.id, "logged on the wrong bike")
    assert stock.level(session, line)["qty"] == 3
    assert inv.open_installation(session, old.id) is not None
    assert old.disposition == "STORED" and old.status == "ACTIVE"
    assert new.disposition == "VOIDED" and inv.open_installation(session, new.id) is None
    assert km(session, old) == 900
    assert next(r for r in stock.consumable_stock(session) if r["id"] == line.id)["available_total"] == 3
    with pytest.raises(DomainError):
        ws_svc.undo(session, ws.id)


def test_installing_existing_spare_takes_it_out_of_spares_and_discard_does_not_subtract_another(session):
    b = bike(session)
    prod = inv.create_product(session, component_type="CHAIN", maker="Shimano", model="CN-M8100")
    a = part(session, "CHAIN", "Chain A", product_id=prod.id)
    spare_b = part(session, "CHAIN", "Chain B", product_id=prod.id)
    spare_c = part(session, "CHAIN", "Chain C", product_id=prod.id)
    inv.install(session, a.id, bike_id=b.id, at="2026-01-01")
    line = stock.add_consumable(session, product_id=prod.id, min_stock=2)
    assert {s["label"] for s in next(r for r in stock.consumable_stock(session) if r["id"] == line.id)
            ["individual_spares"]} == {"Chain B", "Chain C"}
    inv.replace(session, a.id, at="2026-02-01", new_component_id=spare_b.id, old_outcome="DISCARDED")
    row = next(r for r in stock.consumable_stock(session) if r["id"] == line.id)
    assert [s["label"] for s in row["individual_spares"]] == ["Chain C"] and row["available_total"] == 1
    assert row["low"] and stock.shopping_list(session)[0]["suggested_qty"] == 1
    assert spare_c.disposition == "STORED"


def test_counted_stock_rules_and_distinct_transactions(session):
    links = stock.add_consumable(session, component_type="QUICK_LINK", name="KMC 12s quick links")
    assert links.tracking_mode == "COUNTED" and links.unit == "link"
    # a pack of two links is two usable units; packages are recorded separately
    stock.consumable_txn(session, links.id, kind="PURCHASE", qty=4, packages=2, on="2026-01-01", cost_cents=1200)
    stock.consumable_txn(session, links.id, kind="RETURN", qty=2, on="2026-01-05", cost_cents=600, note="wrong size")
    with pytest.raises(DomainError):
        stock.consumable_txn(session, links.id, kind="ADJUST", qty=-1, on="2026-01-06")  # needs a reason
    stock.consumable_txn(session, links.id, kind="ADJUST", qty=-1, on="2026-01-06", note="counted drawer")
    with pytest.raises(DomainError):
        stock.use(session, links.id, qty=0.5, on="2026-01-07")
    with pytest.raises(DomainError, match="Only 1"):
        stock.use(session, links.id, qty=2, on="2026-01-07")
    row = next(r for r in stock.consumable_stock(session) if r["id"] == links.id)
    assert row["stock"]["qty"] == 1 and row["spent_cents"] == 600

    chain = part(session, "CHAIN", "Chain A")
    link = stock.draw_component(session, links.id, on="2026-01-08")   # individual record when used
    inv.install(session, link.id, parent_component_id=chain.id, at="2026-01-08")
    assert stock.level(session, links)["qty"] == 0
    assert inv.location(session, link)["state"] == "INSTALLED"


def test_bulk_supply_use_is_optional_amount_and_costs_count_once(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-01-01")
    wax = stock.add_consumable(session, kind="WAX", name="Silca Hot Melt", unit="g", track_stock=True,
                               container_size=500)
    ws = ws_svc.begin(session, at="2026-02-01", bike_id=b.id)
    stock.consumable_txn(session, wax.id, kind="PURCHASE", qty=500, on="2026-02-01", cost_cents=3999,
                         work_session_id=ws.id)
    m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-02-01", consumable_id=wax.id,
                consumable_qty=None, work_session_id=ws.id)
    summary = ws_svc.summary(session, ws.id)
    assert summary["cost_cents"] == 3999                     # purchase once, the use adds no cost
    assert {t["kind"] for t in summary["transactions"]} == {"STOCK_PURCHASE", "STOCK_USE", "EVENT"}
    row = next(r for r in stock.consumable_stock(session) if r["id"] == wax.id)
    assert row["stock"]["known"] is False                    # amount used unknown is shown honestly


def test_undo_refused_when_later_history_depends_on_it(session):
    b = bike(session)
    old = part(session, "CHAIN", "Chain A")
    inv.install(session, old.id, bike_id=b.id, at="2026-01-01")
    ws = ws_svc.begin(session, at="2026-02-01", bike_id=b.id)
    res = inv.replace(session, old.id, at="2026-02-01", same_product=True, work_session_id=ws.id)
    inv.remove(session, res["new_component_id"], at="2026-03-01")
    with pytest.raises(DomainError, match="later"):
        ws_svc.undo(session, ws.id)


def test_invalid_disposition_rejected_by_database(session):
    c = part(session, "CHAIN", "Chain A")
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE component SET disposition = 'LOST' WHERE id = :i"), {"i": c.id})
    session.rollback()
    assert session.scalar(select(func.count()).select_from(ComponentDisposition)) == 0


def test_replace_with_same_product_takes_a_price(session):
    """UAT B7: 'New item, same product' records what the new one cost."""
    b = bike(session)
    product = inv.create_product(session, component_type="CHAIN", model="CN-M8100")
    old = part(session, "CHAIN", "Chain A", product_id=product.id)
    inv.install(session, old.id, bike_id=b.id, at="2026-09-01")
    res = inv.replace(session, old.id, at="2026-10-05", same_product=True, new={"price_cents": 3499})
    new = session.get(Component, res["new_component_id"])
    assert new.product_id == product.id and new.price_cents == 3499
