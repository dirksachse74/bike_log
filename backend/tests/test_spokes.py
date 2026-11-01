"""Broken spokes logged on the wheel: when it broke, when it was replaced, and the 3rd-spoke alert (DECISIONS 109)."""
import pytest

from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import spokes, stock
from bikelog.services.errors import DomainError

from helpers import bike, part


def _wheel(session):
    b = bike(session)
    rw = part(session, "REAR_WHEEL", "Zipp rear", purchase_date="2026-03-01")
    inv.install(session, rw.id, bike_id=b.id, slot="REAR_WHEEL", at="2026-04-01")
    return b, rw


def _relace(session, rw):
    return next((x for x in m.component_status(session, rw) if x["rule_code"] == "SPOKE_RELACE"), None)


def test_spokes_laced_default_is_the_purchase_date(session):
    _, rw = _wheel(session)
    assert m.spoke_info(session, rw)["laced_default"] == "2026-03-01"
    fw = part(session, "FRONT_WHEEL", "No date")
    assert m.spoke_info(session, fw)["laced_default"] is None


def test_broken_spoke_then_replaced_later_and_third_one_alerts(session):
    b, rw = _wheel(session)
    sp = part(session, "SPOKES", "Sapim rear", prior_usage="UNKNOWN")
    inv.install(session, sp.id, parent_component_id=rw.id, slot="SPOKES", at="2026-03-01")
    line = stock.add_consumable(session, name="Sapim CX-Ray 288", component_type="SPOKES", tracking_mode="COUNTED")
    stock.consumable_txn(session, line.id, kind="PURCHASE", qty=2, on="2026-03-01")

    # 1: broke, not replaced yet → needs attention, shown as open
    res = spokes.log_broken(session, rw.id, broke_on="2026-05-02", note="on the cobbles")
    info = res["spokes"]
    assert info["broken"] == 1 and info["open"] == 1
    assert info["breaks"][0] == {**info["breaks"][0], "broke_on": "2026-05-02", "replaced_on": None,
                                 "note": "on the cobbles", "counted": True}
    assert _relace(session, rw)["status"] == "ATTENTION" and "not replaced yet" in _relace(session, rw)["explanation"]

    # replaced three days later, one spoke from stock
    with pytest.raises(DomainError):
        spokes.mark_replaced(session, rw.id, res["group"], replaced_on="2026-05-01")
    info = spokes.mark_replaced(session, rw.id, res["group"], replaced_on="2026-05-05", stock_line_id=line.id)
    assert info["open"] == 0 and info["breaks"][0]["replaced_on"] == "2026-05-05"
    assert stock.level(session, stock.get(session, line.id))["qty"] == 1
    assert _relace(session, rw)["status"] == "OK"

    # 2: broke and replaced the same day
    info = spokes.log_broken(session, rw.id, broke_on="2026-06-01", replaced_on="2026-06-01")["spokes"]
    assert info["broken"] == 2 and _relace(session, rw)["status"] == "DUE_SOON"

    # 3: the third broken spoke → replace the wheel
    spokes.log_broken(session, rw.id, broke_on="2026-07-01", replaced_on="2026-07-02")
    alert = _relace(session, rw)
    assert alert["status"] == "ATTENTION" and alert["broken_spokes"] == 3
    assert "replace the wheel" in alert["explanation"]
    assert any(x["rule_code"] == "SPOKE_RELACE" for x in m.queue(session, bike_id=b.id))

    # a re-lace (or a new wheel) starts again; the history stays
    m.log_event(session, action_code="WHEEL_RELACE", at="2026-07-10", component_id=rw.id)
    info = m.spoke_info(session, rw)
    assert info["broken"] == 0 and len(info["breaks"]) == 3 and not any(x["counted"] for x in info["breaks"])
    assert _relace(session, rw) is None


def test_replaced_before_it_broke_is_refused_and_wrong_entry_removed(session):
    _, rw = _wheel(session)
    with pytest.raises(DomainError):
        spokes.log_broken(session, rw.id, broke_on="2026-05-02", replaced_on="2026-05-01")
    line = stock.add_consumable(session, name="DT spoke", component_type="SPOKES", tracking_mode="COUNTED")
    stock.consumable_txn(session, line.id, kind="PURCHASE", qty=3, on="2026-03-01")
    g = spokes.log_broken(session, rw.id, broke_on="2026-05-02", replaced_on="2026-05-02",
                          stock_line_id=line.id)["group"]
    assert stock.level(session, stock.get(session, line.id))["qty"] == 2
    info = spokes.remove_broken(session, rw.id, g)
    assert info["broken"] == 0 and info["breaks"] == []
    assert stock.level(session, stock.get(session, line.id))["qty"] == 3      # the stock spoke came back


def test_only_on_a_wheel(session):
    t = part(session, "TIRE", "GP5000")
    with pytest.raises(DomainError):
        spokes.log_broken(session, t.id, broke_on="2026-05-02")
