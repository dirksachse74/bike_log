"""Mount targets inside one part (wheelset page → its wheels' tire positions), with what sits there."""
from bikelog.services import inventory as inv
from bikelog.services import spares

from helpers import bike, part


def test_tire_targets_under_a_wheelset_and_occupant(session):
    b = bike(session)
    ws = part(session, "WHEELSET", "Zipp 303")
    inv.install(session, ws.id, bike_id=b.id, slot="WHEELSET", at="2026-10-01")
    fw, rw = part(session, "FRONT_WHEEL", "Zipp front"), part(session, "REAR_WHEEL", "Zipp rear")
    inv.install(session, fw.id, parent_component_id=ws.id, slot="FRONT_WHEEL", at="2026-10-01")
    inv.install(session, rw.id, parent_component_id=ws.id, slot="REAR_WHEEL", at="2026-10-01")
    other = part(session, "FRONT_WHEEL", "Spare front")
    tire = part(session, "TIRE", "GP5000 rear")
    inv.install(session, tire.id, parent_component_id=rw.id, slot="TIRE", at="2026-10-02")
    t = spares.mount_targets(session, "TIRE", under=ws.id)["targets"]
    assert [(x["parent_label"], x["occupied_by"]) for x in t] == [("Zipp front", None), ("Zipp rear", "GP5000 rear")]
    assert t[1]["occupied_id"] == tire.id and t[0]["parent_type"] == "FRONT_WHEEL"
    only_front = spares.mount_targets(session, "TIRE", under=fw.id)["targets"]
    assert [x["parent_label"] for x in only_front] == ["Zipp front"]
    assert all(x["parent_component_id"] != other.id for x in t)
