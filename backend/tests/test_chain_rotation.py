"""Dirk's chain rotation: two identical Ultegra chains, swap at 500 km, wax both when the second reaches 500."""
from fastapi.testclient import TestClient

from bikelog.api.app import create_app
from bikelog.db import make_session_factory, session_scope
from bikelog.services import chains
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services.reference import ensure_reference_data

from helpers import bike, km, part, ride


def setup(session):
    b = bike(session)
    a = part(session, "CHAIN", "Chain A")
    c = part(session, "CHAIN", "Chain B")
    inv.update_component(session, a.id, mark="1 punch dot next to the quick link")
    inv.update_component(session, c.id, mark="2 punch dots", rotation_bike_id=b.id)
    m.log_batch(session, action_code="WAX_HOT", at="2026-09-01", component_ids=[a.id, c.id])
    inv.install(session, a.id, at="2026-09-01T10:00", bike_id=b.id, slot="CHAIN")
    return b, a, c


def test_rotation_states_prompts_and_one_click_swap(session):
    b, a, c = setup(session)
    assert a.rotation_bike_id == b.id                      # joined by going on the bike
    rot = chains.rotation(session, b.id)
    assert rot["on"] == a.id and rot["next_ready"] == c.id and rot["prompt"] is None
    spare = part(session, "CHAIN", "Chain C")
    assert [x["label"] for x in chains.rotation(session, b.id)["candidates"]] == ["Chain C"]
    inv.update_component(session, spare.id, rotation_bike_id=b.id)
    assert chains.rotation(session, b.id)["candidates"] == []
    inv.update_component(session, spare.id, rotation_bike_id=None)
    assert {r["label"]: r["mark"] for r in rot["chains"]}["Chain B"] == "2 punch dots"
    ride(session, b, "2026-09-10", 460)                    # within the 50 km warning of 500
    rot = chains.rotation(session, b.id)
    assert rot["prompt"]["kind"] == "SWAP" and rot["prompt"]["to"] == c.id
    assert "Swap to Chain B" in rot["prompt"]["text"]
    task = next(t for t in m.queue(session, bike_id=b.id) if t["action_code"] == "WAX_HOT")
    assert task["rotation"]["kind"] == "SWAP" and "Swap to Chain B" in task["explanation"]
    chains.swap(session, b.id, to_component_id=c.id, at="2026-09-11")
    rot = chains.rotation(session, b.id)
    states = {r["label"]: r["state"] for r in rot["chains"]}
    assert rot["on"] == c.id and states["Chain A"] == "NEEDS_HOT_WAX" and rot["next_ready"] is None
    ride(session, b, "2026-09-20", 500)
    rot = chains.rotation(session, b.id)
    assert rot["prompt"]["kind"] == "WAX" and "Chain A" in rot["prompt"]["text"]
    assert set(rot["dirty"]) == {a.id, c.id}
    # wax both; Chain A goes back on, Chain B comes off waxed and ready
    res = chains.wax(session, b.id, component_ids=[a.id, c.id], at="2026-09-21", then_install=a.id)
    assert "Chain B off, Chain A on" in res["text"]
    rot = chains.rotation(session, b.id)
    states = {r["label"]: r["state"] for r in rot["chains"]}
    assert rot["on"] == a.id and states["Chain B"] == "READY_TO_INSTALL" and rot["prompt"] is None
    assert km(session, a) == 460 and km(session, c) == 500
    kinds = [(t["kind"], t["label"]) for t in rot["timeline"]]
    assert kinds[0] == ("ON", "Chain A") and set(kinds[1:3]) == {("WAX", "Chain B"), ("WAX", "Chain A")}
    stints = [t for t in rot["timeline"] if t["kind"] == "ON"]
    assert [(t["label"], t["km"]) for t in stints] == [("Chain A", 0), ("Chain B", 500), ("Chain A", 460)]
    cycles = chains.chain_history(session, a)
    assert [(x["cycle"], x["km"], x["current"]) for x in cycles] == [(1, 460, False), (2, 0, True)]
    assert m.chain_row(session, a)["wax_cycles"] == 2


def test_swap_refuses_the_chain_already_on(session):
    import pytest
    from bikelog.services.errors import DomainError
    b, a, c = setup(session)
    with pytest.raises(DomainError, match="already on"):
        chains.swap(session, b.id, to_component_id=a.id, at="2026-09-02")


def test_chain_rotation_over_http(engine, paths):
    factory = make_session_factory(engine)
    with session_scope(factory) as s:
        ensure_reference_data(s)
        b, a, c = setup(s)
        ids = b.id, a.id, c.id
    bid, aid, cid = ids
    client = TestClient(create_app(factory, paths, token="t", testing=True, static_dir=None))
    client.headers.update({"X-BikeLog-Token": "t"})
    rot = client.get(f"/api/bikes/{bid}/chains").json()
    assert rot["on"] == aid and rot["next_ready"] == cid
    r = client.post(f"/api/bikes/{bid}/chains/swap", json={"to_component_id": cid, "at": "2026-09-05"})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["text"] == "Chain A off, Chain B on."
    ws = r.json()["result"]["work_session_id"]
    assert client.post(f"/api/work-sessions/{ws}/undo", json={"reason": "test"}).status_code == 200
    assert client.get(f"/api/bikes/{bid}/chains").json()["on"] == aid
    r = client.post(f"/api/bikes/{bid}/chains/wax", json={"component_ids": [aid], "at": "2026-09-06"})
    assert r.status_code == 200 and "Hot waxed Chain A" in r.json()["result"]["text"]
    detail = client.get(f"/api/components/{aid}").json()
    assert detail["mark"].startswith("1 punch dot") and len(detail["chain"]["cycles"]) == 2
    assert client.patch(f"/api/components/{aid}", json={"mark": "x" * 81}).status_code in (400, 422)
