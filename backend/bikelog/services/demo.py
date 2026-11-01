"""Development sample data. Only for a database created in demo mode; never touches a personal database."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bikelog.changelog import from_source
from bikelog.models import Bike, Component, Ride
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import rides, settings, stock
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


@from_source("DEMO")
def seed(session: Session, today: date | None = None) -> bool:
    if not is_demo(session):
        raise Protected("Sample data can only be loaded into a demo database (start with --demo).")
    if session.scalar(select(func.count()).select_from(Bike)):
        return False
    today = today or date.today()

    def d(days_ago: int) -> str:
        return (today - timedelta(days=days_ago)).isoformat()

    time_nxr = inv.create_bike(session, name="TIME NXR", maker="TIME", model="NXR", year=2026,
                               strava_gear_id="90000002", starting_km=0, starting_date=d(60))
    bmc = inv.create_bike(session, name="BMC Roadmachine", maker="BMC", strava_gear_id="90000001",
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

    # spare-parts stock: counted per product; installing one gives it its own identity
    pads_prod = inv.create_product(session, component_type="BRAKE_PADS", maker="Shimano", model="L05A-RF resin")
    inv.update_component(session, pads.id, product_id=pads_prod.id)
    pad_stock = stock.add_consumable(session, product_id=pads_prod.id, storage_location="Workshop drawer", min_stock=1)
    stock.consumable_txn(session, pad_stock.id, kind="PURCHASE", qty=3, on=d(40), cost_cents=4797)
    from bikelog.services.spares import set_compatibility
    set_compatibility(session, pads_prod.id, time_nxr.id, True, "fits the TIME NXR calipers")
    set_compatibility(session, pads_prod.id, bmc.id, False, "probably, not checked")
    tube_prod = inv.create_product(session, component_type="INNER_TUBE", maker="Schwalbe", model="SV15 Extralight")
    tube_stock = stock.add_consumable(session, product_id=tube_prod.id, storage_location="Saddle bag box", min_stock=2)
    stock.consumable_txn(session, tube_stock.id, kind="PURCHASE", qty=2, packages=2, on=d(40), cost_cents=1598)
    links = stock.add_consumable(session, component_type="QUICK_LINK", name="KMC 12s quick links",
                                 storage_location="Workshop drawer", min_stock=2)
    stock.consumable_txn(session, links.id, kind="PURCHASE", qty=2, packages=1, on=d(40), cost_cents=899)
    patches = stock.add_consumable(session, name="Park GP-2 patches", tracking_mode="COUNTED", unit="patch",
                                   storage_location="Saddle bag")
    stock.consumable_txn(session, patches.id, kind="PURCHASE", qty=6, packages=1, on=d(40), cost_cents=450)
    old_tube = inv.create_component(session, component_type="INNER_TUBE", label="Rear tube (punctured)",
                                    prior_usage="NEW", product_id=tube_prod.id)
    inv.install(session, old_tube.id, parent_component_id=rear.id, at=d(60), reallocate=False)
    inv.replace(session, old_tube.id, at=d(9), from_stock_id=tube_stock.id, reason="puncture",
                old_outcome="AWAITING_SERVICE")
    session.flush()
    return True


# ---------------------------------------------------------------- sample database (first start)

SAMPLE_NOTE = "Sample data (made up). Settings → Fresh start removes it."


def is_sample(session: Session) -> bool:
    return settings.get(session, "sample_data") == "1"


@from_source("SAMPLE")
def seed_sample(session: Session, today: date | None = None) -> bool:
    """Two made-up bikes with a few months of rides, maintenance and incidents, so a new user can look
    around. Only for a brand-new, empty database (the launcher calls it when it has just created the
    file); every record is logged with source SAMPLE and the database is flagged until Fresh start."""
    if any(session.scalar(select(func.count()).select_from(t)) for t in (Bike, Component, Ride)):
        raise Protected("This database already contains data; sample data is only added to a new database.")
    import random

    from bikelog.services import allocation, groupsets, journal, worksessions
    settings.set_value(session, "sample_data", "1", internal=True)
    today = today or date.today()
    rnd = random.Random(2026)          # same sample every time

    def d(days_ago: int) -> str:
        return (today - timedelta(days=days_ago)).isoformat()

    # Aurora SL: bought in spring, tracked from about two months ago with an estimated odometer
    aurora = inv.create_bike(session, name="Aurora SL", maker="Sample", model="Aurora SL", year=2026,
                             purchase_price_cents=249900, purchase_date=d(235), starting_km=850,
                             starting_date=d(62), starting_is_estimate=True, notes=SAMPLE_NOTE)
    winter = inv.create_bike(session, name="Winter Allroad", maker="Sample", model="Allroad", year=2023,
                             shifting="MECHANICAL", starting_km=4200, starting_date=d(62),
                             starting_is_estimate=True, notes=SAMPLE_NOTE)

    def wheelset(bike, maker, used_km=None):
        front = inv.create_component(session, component_type="FRONT_WHEEL", label=f"{maker} front ({bike.name})",
                                     prior_usage="NEW", tire_setup="TUBE", purchase_date=d(70))
        rear = inv.create_component(session, component_type="REAR_WHEEL", label=f"{maker} rear ({bike.name})",
                                    prior_usage="UNKNOWN" if used_km else "NEW", tire_setup="TUBE",
                                    purchase_date=d(70))
        if used_km:
            inv.set_starting_usage(session, component_id=rear.id, km=used_km, effective=d(62), is_estimate=True,
                                   note="bought used; seller's estimate")
        for wheel, slot in ((front, "FRONT_WHEEL"), (rear, "REAR_WHEEL")):
            inv.install(session, wheel.id, bike_id=bike.id, at=d(62), reallocate=False)
            for ctype, label in (("TIRE", "GP5000 32 mm"), ("INNER_TUBE", "tube")):
                c = inv.create_component(session, component_type=ctype, prior_usage="NEW", purchase_date=d(70),
                                         label=f"{label} {'front' if slot == 'FRONT_WHEEL' else 'rear'} "
                                               f"({bike.name})")
                inv.install(session, c.id, parent_component_id=wheel.id, at=d(62), reallocate=False)
        return front, rear

    a_front, a_rear = wheelset(aurora, "DT Swiss ARC 1400", used_km=1200)
    w_front, w_rear = wheelset(winter, "Alloy")
    inv.group_wheels(session, aurora.id, at=d(61), label="DT Swiss ARC 1400 wheelset")

    ws = worksessions.begin(session, at=d(62), bike_id=aurora.id, title="Ultegra Di2 groupset")
    gs_a = groupsets.import_groupset(session, "SHIMANO_ULTEGRA_DI2_R8100", at=d(62), bike_id=aurora.id,
                                     work_session_id=ws.id, options={"gearing": "52-36", "cassette": "11-34"},
                                     bundle={"price_cents": 165000, "merchant": "Sample shop", "purchased_on": d(70)})
    ws = worksessions.begin(session, at=d(62), bike_id=winter.id, title="GRX 1×12 groupset")
    gs_w = groupsets.import_groupset(session, "SHIMANO_GRX_RX820_1X12", at=d(62), bike_id=winter.id,
                                     work_session_id=ws.id, prior_usage="UNKNOWN")
    a_parts = {r["key"]: r["component_id"] for r in gs_a["items"]}
    w_parts = {r["key"]: r["component_id"] for r in gs_w["items"]}

    # supplies
    wax = stock.add_consumable(session, kind="WAX", name="Hot wax (sample)", unit="g", track_stock=True)
    stock.consumable_txn(session, wax.id, kind="PURCHASE", qty=500, on=d(65), cost_cents=3999)
    drip = stock.add_consumable(session, kind="WAX", name="Wax drip (sample)", unit="ml")
    tube_prod = inv.create_product(session, component_type="INNER_TUBE", maker="Sample", model="Road tube 700×28-32")
    tubes = stock.add_consumable(session, product_id=tube_prod.id, storage_location="Garage shelf", min_stock=2)
    stock.consumable_txn(session, tubes.id, kind="PURCHASE", qty=3, packages=3, on=d(65), cost_cents=2097)

    m.log_event(session, action_code="WAX_HOT", component_id=a_parts["chain"], at=d(62),
                consumable_id=wax.id, consumable_qty=30)
    m.log_event(session, action_code="LUBE", component_id=w_parts["chain"], at=d(62), notes="wet lube for winter")
    m.log_event(session, action_code="BATTERY_CHARGE", component_id=a_parts["battery"], at=d(62))

    # rides: about three a week on the Aurora (some on Zwift), one a week on the Winter Allroad
    names = ["Taunus loop", "Coffee ride", "River path", "Hill repeats", "Club ride", "After work", "Long Sunday",
             "Vineyards", "Gravel detour", "Recovery spin"]
    aurora_rides, winter_rides = [], []
    for days_ago in range(60, 0, -1):
        wd = (today - timedelta(days=days_ago)).weekday()
        if wd in (1, 3, 5) and rnd.random() < 0.85:
            if rnd.random() < 0.2:
                aurora_rides.append(rides.add_manual_ride(
                    session, bike_id=aurora.id, when=d(days_ago) + "T18:30", distance=round(rnd.uniform(25, 40), 1),
                    duration_s=3600, name="Zwift workout", sport_type="VirtualRide"))
            else:
                aurora_rides.append(rides.add_manual_ride(
                    session, bike_id=aurora.id, when=d(days_ago), distance=round(rnd.uniform(35, 120), 1),
                    name=rnd.choice(names), conditions="WET" if rnd.random() < 0.15 else "DRY"))
        elif wd == 6 and rnd.random() < 0.8:
            winter_rides.append(rides.add_manual_ride(
                session, bike_id=winter.id, when=d(days_ago), distance=round(rnd.uniform(40, 90), 1),
                name=rnd.choice(names), conditions="WET" if rnd.random() < 0.5 else "DRY"))

    # maintenance along the way
    m.log_event(session, action_code="WAX_LIQUID", component_id=a_parts["chain"], at=d(45), consumable_id=drip.id)
    m.log_event(session, action_code="WAX_HOT", component_id=a_parts["chain"], at=d(30),
                consumable_id=wax.id, consumable_qty=30)
    m.log_event(session, action_code="BATTERY_CHARGE", component_id=a_parts["battery"], at=d(30))
    m.log_event(session, action_code="CHAIN_MEASURE_WEAR", component_id=a_parts["chain"], at=d(30),
                measurement_value=0.1, measurement_unit="%")
    m.log_event(session, action_code="PAD_MEASURE", component_id=w_parts["pads_rear"], at=d(20),
                measurement_value=1.4, measurement_unit="mm", notes="gritty winter roads")
    m.log_event(session, action_code="LUBE", component_id=w_parts["chain"], at=d(20))
    m.log_event(session, action_code="FREEHUB_SERVICE", component_id=a_rear.id, at=d(75),
                notes="done by the seller before the wheel was sold", cost_cents=4500)

    # incidents on rides
    flat_ride = next(r for r in aurora_rides if r.sport_type == "Ride" and r.ride_date <= d(40))
    rear_tube = next(r["component_id"] for r in inv.bike_setup(session, aurora)
                     if r["component_type"] == "INNER_TUBE" and r["parent_component_id"] == a_rear.id)
    journal.add(session, text="Pinch flat on a pothole, swapped the tube at the roadside.", ride_id=flat_ride.id,
                component_id=rear_tube, incident_type="FLAT", resolved_on=flat_ride.ride_date)
    inv.replace(session, rear_tube, at=flat_ride.ride_date + "T12:00", from_stock_id=tubes.id, reason="pinch flat",
                old_outcome="AWAITING_SERVICE")
    crash_ride = next((r for r in reversed(winter_rides) if r.ride_date <= d(10)), winter_rides[-1])
    journal.add(session, text="Slid out on wet leaves in a corner; scraped bar tape and rear derailleur.",
                ride_id=crash_ride.id, incident_type="CRASH")
    creak_ride = aurora_rides[-1] if aurora_rides[-1].sport_type == "Ride" else aurora_rides[-2]
    journal.add(session, text="Creak under load from the bottom bracket area.", ride_id=creak_ride.id,
                component_id=a_parts["crankset"], incident_type="DEFECT")
    journal.add(session, text="Fitted 32 mm tires; clearance is fine.", on=d(62), bike_id=aurora.id)

    session.flush()
    allocation.rebuild_all(session, settings.tz(session))
    return True
