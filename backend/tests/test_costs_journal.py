"""Prices, bike initial/running cost (counted once, derived from records) and the journal."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bikelog.services import costs, journal, stock
from bikelog.services import groupsets as gs
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import worksessions as ws_svc
from bikelog.services.errors import DomainError

from helpers import bike, part, ride


def test_initial_and_running_cost_count_each_euro_once(session):
    b = bike(session, purchase_price_cents=420000, purchase_date="2026-03-01")
    other = bike(session, name="BMC Roadmachine")
    rear = part(session, "REAR_WHEEL", "Rear wheel", price_cents=60000)
    inv.install(session, rear.id, bike_id=b.id, at="2026-08-01")
    cassette = part(session, "CASSETTE", "Cassette", price_cents=9000)
    inv.install(session, cassette.id, parent_component_id=rear.id, at="2026-08-01")   # counts via the wheel
    chain = part(session, "CHAIN", "Chain A", price_cents=4000)
    inv.install(session, chain.id, bike_id=b.id, at="2026-08-01")
    inv.move(session, chain.id, bike_id=other.id, at="2026-09-01")                   # stays with the first bike
    part(session, "CHAIN", "Chain B", price_cents=3500)                               # spare: no bike
    original = part(session, "SADDLE", "Stock saddle")                                # no price: listed as unpriced
    inv.install(session, original.id, bike_id=b.id, at="2026-03-01")
    # stock: 3 pad sets for 45 €, one used on this bike
    pads = stock.add_consumable(session, name="L05A-RF", tracking_mode="COUNTED", component_type="BRAKE_PADS")
    stock.consumable_txn(session, pads.id, kind="PURCHASE", qty=3, on="2026-08-01", cost_cents=4500)
    drawn = stock.draw_component(session, pads.id, on="2026-08-02", label="Pads from stock")
    inv.install(session, drawn.id, bike_id=b.id, slot="FRONT_PADS", at="2026-08-02")
    # service with a shop fee
    m.log_event(session, action_code="SERVICE", component_id=chain.id, bike_id=b.id, at="2026-08-20",
                cost_cents=2500, work_done="shop check")
    c = costs.bike_costs(session, b)
    assert c["initial_cents"] == 420000
    assert c["parts_cents"] == 60000 + 9000 + 4000
    assert c["stock_cents"] == 1500 and c["estimated"]                               # average unit price
    assert c["services_cents"] == 2500
    assert c["running_cents"] == 73000 + 1500 + 2500
    assert c["total_cents"] == 420000 + 77000
    assert c["unpriced_parts"] == 1 and c["unpriced_labels"] == ["Stock saddle"]
    assert costs.bike_costs(session, other)["running_cents"] == 0
    ride(session, b, "2026-08-21", 100)


def test_undone_session_costs_drop_out_and_groupset_prices(session):
    b = bike(session)
    ws = ws_svc.begin(session, at="2026-10-25", bike_id=b.id, title="Groupset")
    res = gs.import_groupset(session, "SHIMANO_ULTEGRA_DI2_R8100", bike_id=b.id, at="2026-10-25",
                             work_session_id=ws.id, prices={"crankset": 45000, "chain": 4500})
    assert costs.bike_costs(session, b)["parts_cents"] == 49500
    with pytest.raises(DomainError, match="not part of this import"):
        ws2 = ws_svc.begin(session, at="2026-10-25", title="x")
        gs.import_groupset(session, "SHIMANO_ULTEGRA_DI2_R8100", at="2026-10-25", work_session_id=ws2.id,
                           include=["chain"], prices={"crankset": 1})
    ws_svc.undo(session, res["work_session_id"], "test")
    assert costs.bike_costs(session, b)["parts_cents"] == 0


def test_prices_cannot_be_negative_and_product_reference_price(session):
    with pytest.raises(DomainError, match="negative"):
        bike(session, purchase_price_cents=-1)
    p = inv.create_product(session, component_type="CHAIN", maker="Shimano", model="CN-M8100", list_price_cents=4999)
    assert inv.update_product(session, p.id, list_price_cents=4599).list_price_cents == 4599
    c = part(session, "CHAIN", "Chain A", product_id=p.id)
    b = bike(session)
    inv.install(session, c.id, bike_id=b.id, at="2026-10-01")
    assert costs.bike_costs(session, b)["parts_cents"] == 0      # a reference price is not money spent


def test_journal_on_bike_and_part_with_issue_and_maintenance_notes(session):
    b = bike(session)
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-10-01")
    e1 = journal.add(session, bike_id=b.id, on="2026-10-05", text="Creak from the bottom bracket area")
    e2 = journal.add(session, component_id=chain.id, on="2026-10-06", kind="ISSUE", text="Skips on 15T under load")
    assert e2.bike_id == b.id                                    # part entries remember the bike
    m.log_event(session, action_code="REPAIR", component_id=chain.id, at="2026-10-07", symptom="skipping",
                work_done="replaced quick link", outcome="RESOLVED")
    part_rows = journal.entries(session, component_id=chain.id)
    assert [r["source"] for r in part_rows] == ["MAINTENANCE", "JOURNAL"]
    assert part_rows[1]["open_issue"]
    journal.update(session, e2.id, resolved_on="2026-10-07")
    assert not journal.entries(session, component_id=chain.id)[1]["open_issue"]
    bike_rows = journal.entries(session, bike_id=b.id)
    assert {r["text"] for r in bike_rows if r["source"] == "JOURNAL"} == {e1.text, e2.text}
    journal.void(session, e1.id, "wrong bike")
    assert e1.text not in {r["text"] for r in journal.entries(session, bike_id=b.id)}
    assert e1.text in {r["text"] for r in journal.entries(session, bike_id=b.id, include_voided=True)}
    with pytest.raises(DomainError):
        journal.add(session, bike_id=b.id, on="2026-10-05", text="   ")
    with pytest.raises(IntegrityError, match="PROTECTED"):
        session.execute(text("DELETE FROM journal_entry WHERE id = :i"), {"i": e1.id})
