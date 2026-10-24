import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bikelog.services import inventory as inv
from bikelog.services.errors import Conflict, DomainError, Protected
from bikelog.services.usage import component_ledger

from helpers import bike, km, part, ride


def test_bike_and_component_instances_are_distinct_from_product_models(session):
    b = bike(session)
    prod = inv.create_product(session, component_type="CHAIN", maker="Shimano", model="CN-M8100",
                              specs={"speeds": 12}, spec_source="manufacturer datasheet", spec_version="2024")
    a = part(session, "CHAIN", "Chain A", product_id=prod.id)
    c = part(session, "CHAIN", "Chain B", product_id=prod.id)
    assert a.id != c.id and a.uuid != c.uuid and a.product_id == c.product_id == prod.id
    assert b.uuid
    with pytest.raises(DomainError):
        inv.create_component(session, component_type="CASSETTE", label="X", product_id=prod.id)


def test_quick_add_needs_only_type_and_label(session):
    c = inv.create_component(session, component_type="SADDLE", label="Short saddle")
    assert c.prior_usage == "UNKNOWN"
    with pytest.raises(DomainError):
        inv.create_component(session, component_type="SADDLE", label="  ")


def test_three_individually_labelled_chains(session):
    for label in ("Chain A", "Chain B", "Chain C"):
        part(session, "CHAIN", label)
    with pytest.raises(Conflict):
        part(session, "CHAIN", "chain a")


def test_install_remove_reinstall_preserves_lifetime_across_bikes(session):
    time_nxr, bmc = bike(session), bike(session, "BMC Roadmachine")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=bmc.id, at="2026-08-01")
    ride(session, bmc, "2026-08-10", 100)
    inv.remove(session, chain.id, at="2026-08-20", reason="rotation")
    ride(session, bmc, "2026-08-21", 50)            # chain in storage: no usage
    inv.install(session, chain.id, bike_id=time_nxr.id, at="2026-09-01")
    ride(session, time_nxr, "2026-09-02", 30)
    assert km(session, chain) == 130
    hist = inv.installation_history(session, chain)
    assert [h["km"] for h in hist] == [100, 30]
    assert [e["km"] for e in component_ledger(session, chain)] == [100, 30]


def test_replace_and_replace_with_same_product(session):
    b = bike(session)
    prod = inv.create_product(session, component_type="TIRE", model="GP5000 S TR 28")
    rear = part(session, "REAR_WHEEL", "Rear wheel")
    inv.install(session, rear.id, bike_id=b.id, at="2026-01-01")
    tire = part(session, "TIRE", "Rear tire", product_id=prod.id)
    inv.install(session, tire.id, parent_component_id=rear.id, at="2026-01-01")
    ride(session, b, "2026-02-01", 80)
    res = inv.replace(session, tire.id, at="2026-03-01", same_product=True)
    new = inv.get_component(session, res["new_component_id"])
    assert new.product_id == prod.id and new.id != tire.id and new.label == "Rear tire (2)"
    ride(session, b, "2026-03-05", 40)
    assert km(session, tire) == 80 and km(session, new) == 40 and km(session, rear) == 120
    assert inv.location(session, tire)["state"] == "STORED"


def test_conflicting_installations_are_prevented(session):
    b1, b2 = bike(session), bike(session, "BMC")
    a, c = part(session, "CHAIN", "Chain A"), part(session, "CHAIN", "Chain B")
    inv.install(session, a.id, bike_id=b1.id, at="2026-05-01")
    with pytest.raises(Conflict):           # same part on two bikes
        inv.install(session, a.id, bike_id=b2.id, at="2026-06-01")
    with pytest.raises(Conflict):           # slot occupied
        inv.install(session, c.id, bike_id=b1.id, at="2026-06-01")
    with pytest.raises(Conflict):           # historical period overlapping the open one
        inv.install(session, c.id, bike_id=b1.id, at="2026-04-01", until="2026-05-10")
    inv.install(session, c.id, bike_id=b1.id, at="2026-04-01", until="2026-05-01")  # touching is fine (end-exclusive)


def test_database_itself_rejects_overlapping_installation(session):
    b = bike(session)
    a = part(session, "CHAIN", "Chain A")
    inv.install(session, a.id, bike_id=b.id, at="2026-05-01", until="2026-06-01")
    session.commit()
    with pytest.raises(IntegrityError, match="CONFLICT"):
        session.execute(text(
            "INSERT INTO installation (uuid, component_id, bike_id, slot, installed_at, installed_utc, created_at) "
            "VALUES ('x', :c, :b, 'CHAIN', '2026-05-15', '2026-05-14T22:00:00Z', 'now')"), {"c": a.id, "b": b.id})
    session.rollback()


def test_no_hard_delete_of_component_with_history(session):
    b = bike(session)
    a = part(session, "CHAIN", "Chain A")
    inv.install(session, a.id, bike_id=b.id, at="2026-05-01")
    with pytest.raises(Protected):
        inv.delete_component(session, a.id)
    session.commit()
    with pytest.raises(IntegrityError, match="PROTECTED"):
        session.execute(text("DELETE FROM component WHERE id = :c"), {"c": a.id})
    session.rollback()
    unused = part(session, "CHAIN", "Typo chain")
    inv.delete_component(session, unused.id)


def test_retire_keeps_history_and_blocks_install(session):
    b = bike(session)
    a = part(session, "CHAIN", "Chain A")
    inv.install(session, a.id, bike_id=b.id, at="2026-05-01")
    ride(session, b, "2026-05-02", 25)
    inv.retire_component(session, a.id, on="2026-06-01", reason="worn 0.5%")
    assert km(session, a) == 25 and inv.location(session, a)["state"] == "RETIRED"
    with pytest.raises(DomainError):
        inv.install(session, a.id, bike_id=b.id, at="2026-07-01")


def test_correction_is_separate_from_replacement(session):
    b = bike(session)
    a, c = part(session, "CHAIN", "Chain A"), part(session, "CHAIN", "Chain B")
    wrong = inv.install(session, a.id, bike_id=b.id, at="2026-05-01")
    ride(session, b, "2026-05-02", 25)
    inv.void_installation(session, wrong.id, reason="was Chain B all along")
    inv.install(session, c.id, bike_id=b.id, at="2026-05-01")
    assert km(session, a) == 0 and km(session, c) == 25
    assert inv.installation_history(session, a)[0]["voided"] is True


def test_component_tree_follows_wheel_moves(session):
    b1, b2 = bike(session), bike(session, "BMC")
    wheel = part(session, "REAR_WHEEL", "Zipp rear")
    tire = part(session, "TIRE", "GP5000 rear")
    inv.install(session, wheel.id, bike_id=b1.id, at="2026-01-01")
    inv.install(session, tire.id, parent_component_id=wheel.id, at="2026-01-01")
    ride(session, b1, "2026-01-05", 60)
    inv.remove(session, wheel.id, at="2026-02-01")
    inv.install(session, wheel.id, bike_id=b2.id, at="2026-02-01")
    ride(session, b2, "2026-02-03", 40)
    assert km(session, tire) == 100
    assert "BMC" in inv.location(session, tire)["text"]
