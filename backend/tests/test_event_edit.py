"""Maintenance log: edit an entry in place, delete it (voided, restorable), restore it (Dirk 2026-11-01)."""
import pytest

from bikelog import changelog
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import worksessions
from bikelog.services.errors import DomainError

from helpers import bike, part, ride


def hot_wax(session, chain):
    return next(r for r in m.component_status(session, chain) if r["action_code"] == "WAX_HOT")


def test_edit_delete_restore_entry(session):
    b = bike(session, purchase_date="2026-09-01")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-09-01")
    wax = m.add_consumable(session, kind="WAX", name="Silca Hot Melt", unit="g", track_stock=True)
    m.consumable_txn(session, wax.id, kind="PURCHASE", qty=500, on="2026-09-01", cost_cents=3999)
    ride(session, b, "2026-09-10", 300)
    ev = m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-09-20", consumable_id=wax.id,
                     consumable_qty=20, cost_cents=500)
    ride(session, b, "2026-09-25", 100)
    assert hot_wax(session, chain)["used_km"] == 100
    # edit: date moved back, so the ride on the 10th now counts after the wax
    m.update_event(session, ev.id, at="2026-09-05", notes="new pot", cost_cents=700)
    assert ev.performed_on == "2026-09-05" and hot_wax(session, chain)["used_km"] == 400
    rows = changelog.entries(session, component_id=chain.id)
    assert any(r["action"] == "ENTRY_CHANGED" and r["field"].endswith("cost") and r["new_value"] == "€7.00" for r in rows)
    with pytest.raises(DomainError, match="cannot be changed"):
        m.update_event(session, ev.id, action_code="WAX_LIQUID")
    # delete: out of the log's counts, supplies back in stock, recorded in the change log
    m.void_event(session, ev.id, "deleted")
    assert hot_wax(session, chain)["last_done"] is None
    assert next(s for s in m.consumable_stock(session) if s["id"] == wax.id)["stock"]["qty"] == 500
    assert changelog.entries(session, component_id=chain.id)[0]["action"] == "ENTRY_DELETED"
    with pytest.raises(DomainError, match="restore it first"):
        m.update_event(session, ev.id, notes="x")
    # restore: back as it was, stock used again
    m.restore_event(session, ev.id)
    assert hot_wax(session, chain)["last_done"] == "2026-09-05"
    assert next(s for s in m.consumable_stock(session) if s["id"] == wax.id)["stock"]["qty"] == 480
    assert changelog.entries(session, component_id=chain.id)[0]["action"] == "ENTRY_RESTORED"


def test_entry_undone_with_its_session_is_not_restored_alone(session):
    b = bike(session, purchase_date="2026-09-01")
    chain = part(session, "CHAIN", "Chain A")
    inv.install(session, chain.id, bike_id=b.id, at="2026-09-01")
    ws = worksessions.begin(session, at="2026-09-20", bike_id=b.id)
    ev = m.log_event(session, action_code="WAX_HOT", component_id=chain.id, at="2026-09-20", work_session_id=ws.id)
    worksessions.undo(session, ws.id, "typo")
    with pytest.raises(DomainError, match="Undo"):
        m.restore_event(session, ev.id)
