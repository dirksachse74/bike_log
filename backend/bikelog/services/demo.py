"""Development sample data. Only for a database created in demo mode; never touches a personal database."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.models import Bike, Component, Ride
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import rides, settings
from bikelog.services.errors import Protected


def is_demo(session: Session) -> bool:
    return settings.get(session, "demo_mode") == "1"


def mark_demo_database(session: Session) -> None:
    """Called only by the launcher for the separate demo data directory, on an empty database."""
    if is_demo(session):
        return
    if any(session.scalar(select(func.count()).select_from(t)) for t in (Bike, Component, Ride)):
        raise Protected("This database already contains data; demo mode refuses to use it.")
    settings.set_value(session, "demo_mode", "1", internal=True)


def seed(session: Session, today: date | None = None) -> bool:
    if not is_demo(session):
        raise Protected("Sample data can only be loaded into a demo database (start with --demo).")
    if session.scalar(select(func.count()).select_from(Bike)):
        return False
    today = today or date.today()

    def d(days_ago: int) -> str:
        return (today - timedelta(days=days_ago)).isoformat()

    time_nxr = inv.create_bike(session, name="TIME NXR", maker="TIME", model="NXR", year=2026,
                               strava_gear_id="18842913", starting_km=0, starting_date=d(60))
    bmc = inv.create_bike(session, name="BMC Roadmachine", maker="BMC", strava_gear_id="13071041",
                          starting_km=17000, starting_date=d(90), starting_is_estimate=True)
    chain_prod = inv.create_product(session, component_type="CHAIN", maker="Shimano", model="CN-M8100 12s",
                                    specs={"speeds": 12, "links": 116}, spec_source="manufacturer datasheet")
    a = inv.create_component(session, component_type="CHAIN", label="Chain A", product_id=chain_prod.id,
                             prior_usage="UNKNOWN")
    inv.set_starting_usage(session, component_id=a.id, km=1000, effective=d(45), is_estimate=True,
                           note="estimated from Strava totals")
    b = inv.create_component(session, component_type="CHAIN", label="Chain B", product_id=chain_prod.id, prior_usage="NEW")
    c = inv.create_component(session, component_type="CHAIN", label="Chain C", product_id=chain_prod.id, prior_usage="NEW")
    rear = inv.create_component(session, component_type="REAR_WHEEL", label="Reynolds rear", prior_usage="NEW")
    front = inv.create_component(session, component_type="FRONT_WHEEL", label="Reynolds front", prior_usage="NEW")
    tire_r = inv.create_component(session, component_type="TIRE", label="GP5000 rear", prior_usage="NEW")
    tire_f = inv.create_component(session, component_type="TIRE", label="GP5000 front", prior_usage="NEW")
    brake_f = inv.create_component(session, component_type="BRAKE_CIRCUIT", label="Front brake (NXR)", prior_usage="UNKNOWN")
    brake_r = inv.create_component(session, component_type="BRAKE_CIRCUIT", label="Rear brake (NXR)", prior_usage="NEW")
    pads = inv.create_component(session, component_type="BRAKE_PADS", label="Rear pads (NXR)", prior_usage="NEW")
    bmc_chain = inv.create_component(session, component_type="CHAIN", label="BMC chain", prior_usage="UNKNOWN")

    for comp, kw in ((rear, {"bike_id": time_nxr.id}), (front, {"bike_id": time_nxr.id}),
                     (tire_r, {"parent_component_id": rear.id}), (tire_f, {"parent_component_id": front.id}),
                     (brake_f, {"bike_id": time_nxr.id, "slot": "FRONT_BRAKE"}),
                     (brake_r, {"bike_id": time_nxr.id, "slot": "REAR_BRAKE"}),
                     (pads, {"bike_id": time_nxr.id, "slot": "REAR_PADS"})):
        inv.install(session, comp.id, at=d(60), reallocate=False, **kw)
    inv.install(session, bmc_chain.id, bike_id=bmc.id, at=d(90), reallocate=False)
    # chain C first, then B, then A (rotation)
    inv.install(session, c.id, bike_id=time_nxr.id, at=d(60), until=d(34), reallocate=False)
    m.log_event(session, action_code="WAX_HOT", component_id=c.id, at=d(61))
    inv.install(session, b.id, bike_id=time_nxr.id, at=d(34), until=d(20), reallocate=False)
    m.log_event(session, action_code="WAX_HOT", component_id=b.id, at=d(35))
    inv.install(session, a.id, bike_id=time_nxr.id, at=d(20))
    m.log_event(session, action_code="WAX_HOT", component_id=a.id, at=d(20))

    for days, km, name in ((58, 72.0, "Taunus loop"), (50, 88.5, "Vogelsberg"), (41, 95.0, "Spessart"),
                           (36, 64.0, "After work"), (30, 110.2, "Odenwald"), (24, 40.0, "Coffee ride")):
        rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(days), distance=km, name=name)
    m.log_event(session, action_code="WAX_HOT", component_id=b.id, at=d(19), notes="re-waxed after removal")
    for days, km, name in ((18, 78.4, "Main river"), (15, 102.6, "Feldberg"), (12, 89.0, "Wetterau")):
        rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(days), distance=km, name=name)
    m.log_event(session, action_code="WAX_LIQUID", component_id=a.id, at=d(11))
    rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(8), distance=45.0, name="Recovery")
    rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(6) + "T18:30", distance=35.0, name="Zwift race",
                          sport_type="VirtualRide", duration_s=3600)
    rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(4), distance=131.0, name="Long Sunday ride")
    rides.add_manual_ride(session, bike_id=time_nxr.id, when=d(3), distance=64.0, name="Club ride",
                          assignment_uncertain=True, uncertainty_note="Might have been the BMC")
    excluded = rides.add_manual_ride(session, bike_id=bmc.id, when=d(5), distance=55.0, name="Duplicate entry")
    rides.exclude_ride(session, excluded.id, "entered twice")
    rides.add_manual_ride(session, bike_id=bmc.id, when=d(10), distance=70.0, name="Rain bike ride")

    m.log_event(session, action_code="BRAKE_FLUID_REPLACE", component_id=brake_r.id, at=d(220),
                work_done="full flush, Shimano mineral oil")
    m.log_event(session, action_code="BRAKE_BLEED", component_id=brake_r.id, at=d(12), symptom="spongy lever",
                work_done="lever bleed", outcome="IMPROVED")
    m.log_event(session, action_code="CHAIN_MEASURE_WEAR", component_id=a.id, at=d(11), measurement_value=0.25,
                measurement_unit="%", outcome="OK")
    wax = m.add_consumable(session, kind="WAX", name="Silca Secret Chain Blend", unit="g", track_stock=True)
    m.consumable_txn(session, wax.id, kind="PURCHASE", qty=500, on=d(70), cost_cents=3999)
    m.add_consumable(session, kind="WAX", name="Silca Super Secret drip", unit="ml")
    m.add_consumable(session, kind="BRAKE_FLUID", name="Shimano mineral oil", unit="ml")
    session.flush()
    return True
