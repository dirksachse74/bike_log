"""The frame in Costs (Dirk 2026-11-01, DECISIONS 113): shown, priced, never counted twice."""
from bikelog.models import Component
from bikelog.services import costs
from bikelog.services import groupsets as gs
from bikelog.services import inventory as inv
from bikelog.services import worksessions as ws_svc
from bikelog.services.frames import ensure_frames

from helpers import bike, part


def test_bike_built_from_a_frame_frame_price_is_the_initial_cost(session):
    b = bike(session, name="Synapse")
    ensure_frames(session, b.id)
    c = costs.bike_costs(session, b)
    assert c["frame"]["counted"] == "NO_PRICE" and c["initial_cents"] is None
    frame = inv.get_component(session, c["frame"]["component_id"])
    inv.update_component(session, frame.id, price_cents=199900, purchase_date="2025-03-01", shop="Bike24")
    c = costs.bike_costs(session, b)
    assert c["frame"] == {**c["frame"], "counted": "INITIAL", "price_cents": 199900, "shop": "Bike24"}
    assert c["initial_cents"] == 199900 and c["initial_source"] == "FRAME" and c["purchase_date"] == "2025-03-01"
    assert c["parts_cents"] == 0 and c["total_cents"] == 199900          # not a running cost as well


def test_complete_bike_frame_price_is_included_not_counted_twice(session):
    b = bike(session, name="Roadmachine", purchase_price_cents=420000, purchase_date="2026-03-01")
    ensure_frames(session, b.id)
    frame_id = costs.bike_costs(session, b)["frame"]["component_id"]
    inv.update_component(session, frame_id, price_cents=150000)
    c = costs.bike_costs(session, b)
    assert c["frame"]["counted"] == "INCLUDED" and c["initial_cents"] == 420000 and c["total_cents"] == 420000
    # a warranty frame later is a running cost
    new = part(session, "FRAME", "Warranty frame", price_cents=50000)
    inv.replace(session, frame_id, new_component_id=new.id, at="2026-09-01")
    c = costs.bike_costs(session, b)
    assert c["frame"]["label"] == "Warranty frame" and c["frame"]["counted"] == "PART"
    assert c["parts_cents"] == 50000 and c["total_cents"] == 470000


def test_groupset_bundle_row_links_to_the_groupset_page(session):
    b = bike(session)
    ws = ws_svc.begin(session, at="2026-10-25", bike_id=b.id, title="Groupset")
    gs.import_groupset(session, "SHIMANO_ULTEGRA_DI2_R8100", bike_id=b.id, at="2026-10-25", work_session_id=ws.id,
                       bundle={"name": "Ultegra Di2", "price_cents": 180000})
    row = next(i for i in costs.bike_costs(session, b)["items"] if i["kind"] == "BUNDLE")
    assert row["groupset"] is True


def test_wheels_and_spokes_of_a_priced_wheelset_are_not_missing_a_price(session):
    """Dirk 2026-11-01: wheels and spokes inside a priced wheelset were listed as 'no price'."""
    from bikelog.services.wheels import ensure_wheels
    b = bike(session, name="Synapse", purchase_price_cents=300000, purchase_date="2026-03-01")
    ws = part(session, "WHEELSET", "9Velo LV WIDE", price_cents=120000, purchase_date="2026-03-01")
    inv.install(session, ws.id, bike_id=b.id, slot="WHEELSET", at="2026-04-01")
    ensure_wheels(session, ws.id)
    wheels = [c for c in session.query(Component).filter(Component.component_type.in_(("FRONT_WHEEL", "REAR_WHEEL")))]
    assert len(wheels) == 2
    for w in wheels:
        sp = part(session, "SPOKES", f"Spokes {w.label}", prior_usage="UNKNOWN")
        inv.install(session, sp.id, parent_component_id=w.id, slot="SPOKES", at="2026-04-01")
    tire = part(session, "TIRE", "GP5000 front")
    inv.install(session, tire.id, parent_component_id=wheels[0].id, slot="TIRE", at="2026-04-02")
    c = costs.bike_costs(session, b)
    assert c["parts_cents"] == 120000
    assert c["unpriced_labels"] == ["GP5000 front"]       # a tire is bought on its own: still asks for a price
    # without a wheelset price, the wheels and spokes do ask for one
    inv.update_component(session, ws.id, price_cents=None)
    c = costs.bike_costs(session, b)
    assert c["unpriced_parts"] == 6 and "9Velo LV WIDE" in c["unpriced_labels"]
