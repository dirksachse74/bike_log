"""Ride → component usage allocation.

``usage_contribution`` is the only source of component usage. For every ride it is replaced as a
whole (delete + insert), never appended, so repeating any operation cannot double-count.

Which parts a ride used, in priority order:
1. explicit ride equipment for a bike slot (``ride_equipment``; component NULL = slot not used),
2. otherwise installation history at the ride's instant (start-inclusive, end-exclusive),
   resolved as a tree (bike → wheel → tire),
3. then the ride's usage profile removes excluded slots / types (e.g. direct-drive trainer).

Contributions before a component's starting-mileage date are kept as IN_BASELINE (already inside
the starting value) and do not count.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bikelog.models import (
    Component, Installation, Ride, RideEquipment, RideFlag, UsageAdjustment, UsageContribution, UsageProfile,
)
from bikelog.timeutil import FAR_FUTURE, local_date_of


@dataclass
class _Inst:
    id: int
    component_id: int
    bike_id: int | None
    parent_id: int | None
    slot: str
    start: str
    end: str
    start_date_only: bool
    end_date_only: bool
    start_local: str
    end_local: str | None


class AllocationIndex:
    """All non-voided installations, starting values, component types and profiles, loaded once."""

    def __init__(self, session: Session, tz: str):
        self.tz = tz
        self.by_bike: dict[int, list[_Inst]] = defaultdict(list)
        self.by_parent: dict[int, list[_Inst]] = defaultdict(list)
        for i in session.scalars(select(Installation).where(Installation.voided_at.is_(None))):
            rec = _Inst(
                i.id, i.component_id, i.bike_id, i.parent_component_id, i.slot, i.installed_utc,
                i.removed_utc or FAR_FUTURE, len(i.installed_at) == 10, bool(i.removed_at and len(i.removed_at) == 10),
                local_date_of(i.installed_utc, tz), local_date_of(i.removed_utc, tz) if i.removed_utc else None,
            )
            (self.by_bike[i.bike_id] if i.bike_id is not None else self.by_parent[i.parent_component_id]).append(rec)
        self.baseline: dict[int, str] = {}
        for a in session.scalars(select(UsageAdjustment).where(
                UsageAdjustment.kind == "STARTING", UsageAdjustment.voided_at.is_(None),
                UsageAdjustment.component_id.is_not(None))):
            self.baseline[a.component_id] = a.effective_utc
        self.types = dict(session.execute(select(Component.id, Component.component_type)).all())
        self.profiles: dict[int, tuple[set[str], set[str]]] = {}
        for p in session.scalars(select(UsageProfile)):
            self.profiles[p.id] = (set(json.loads(p.excluded_slots_json)), set(json.loads(p.excluded_types_json)))

    @staticmethod
    def _active(insts: list[_Inst], t: str) -> list[_Inst]:
        return [i for i in insts if i.start <= t < i.end]

    def subtree(self, component_id: int, t: str) -> list[_Inst]:
        out: list[_Inst] = []
        for child in self._active(self.by_parent.get(component_id, []), t):
            out.append(child)
            out.extend(self.subtree(child.component_id, t))
        return out

    def boundary_days(self, insts: list[_Inst], slot: str) -> dict[str, bool]:
        """Local dates on which the slot changed -> whether that boundary is date-only."""
        days: dict[str, bool] = {}
        for i in insts:
            if i.slot != slot:
                continue
            days[i.start_local] = days.get(i.start_local, False) or i.start_date_only
            if i.end_local:
                days[i.end_local] = days.get(i.end_local, False) or i.end_date_only
        return days


@dataclass
class _Use:
    component_id: int
    root_slot: str
    slot: str
    basis: str
    ambiguous: bool


def _plan(index: AllocationIndex, ride: Ride, explicit: dict[str, int | None]) -> tuple[list[_Use], list[tuple[str, str | None, str]]]:
    flags: list[tuple[str, str | None, str]] = []
    if ride.bike_id is None:
        flags.append(("NO_BIKE", None, "No bike assigned: this ride gives no component usage until you pick a bike."))
        return [], flags
    t = ride.sort_utc
    ride_date_only = ride.start_time_utc is None
    bike_insts = index.by_bike.get(ride.bike_id, [])
    uses: list[_Use] = []
    ambiguous_slots: set[str] = set()
    for slot in {i.slot for i in bike_insts}:
        if slot in explicit:
            continue
        days = index.boundary_days(bike_insts, slot)
        if ride.ride_date in days and (days[ride.ride_date] or ride_date_only):
            ambiguous_slots.add(slot)
            flags.append(("AMBIGUOUS_CHANGE_DATE", slot,
                          f"{slot.replace('_', ' ').title()} changed on {ride.ride_date} without a clock time; "
                          "this ride was allocated to the part installed that day. Confirm the equipment to resolve."))
    for inst in index._active(bike_insts, t):
        if inst.slot in explicit:
            continue
        amb = inst.slot in ambiguous_slots
        uses.append(_Use(inst.component_id, inst.slot, inst.slot, "HISTORY", amb))
        for child in index.subtree(inst.component_id, t):
            uses.append(_Use(child.component_id, inst.slot, child.slot, "HISTORY", amb))
    for slot, comp_id in explicit.items():
        if comp_id is None:
            continue
        uses.append(_Use(comp_id, slot, slot, "EXPLICIT", False))
        for child in index.subtree(comp_id, t):
            uses.append(_Use(child.component_id, slot, child.slot, "EXPLICIT", False))
    if ride.usage_profile_id and ride.usage_profile_id in index.profiles:
        ex_slots, ex_types = index.profiles[ride.usage_profile_id]
        uses = [u for u in uses if u.root_slot not in ex_slots and u.slot not in ex_slots
                and index.types.get(u.component_id) not in ex_types]
    # one row per component (a part cannot be used twice by one ride)
    seen: dict[int, _Use] = {}
    for u in uses:
        if u.component_id not in seen or u.basis == "EXPLICIT":
            seen[u.component_id] = u
    return list(seen.values()), flags


def allocate_ride(session: Session, ride: Ride, index: AllocationIndex) -> None:
    session.execute(delete(UsageContribution).where(UsageContribution.ride_id == ride.id))
    session.execute(delete(RideFlag).where(RideFlag.ride_id == ride.id))
    if ride.status != "ACTIVE" or ride.inclusion != "INCLUDED":
        session.flush()
        return
    explicit = {e.slot: e.component_id for e in session.scalars(
        select(RideEquipment).where(RideEquipment.ride_id == ride.id))}
    uses, flags = _plan(index, ride, explicit)
    if ride.distance_km is None:
        flags.append(("MISSING_DISTANCE", None, "Distance is missing: 0 km counted; time still counts."))
    if ride.assignment_uncertain:
        flags.append(("UNCERTAIN_ASSIGNMENT", None,
                      ride.uncertainty_note or "Marked as uncertain: bike or equipment may be wrong."))
    km = ride.distance_km or 0.0
    for u in uses:
        base = index.baseline.get(u.component_id)
        in_baseline = base is not None and ride.sort_utc < base
        certain = not (u.ambiguous or ride.assignment_uncertain)
        note = None
        if u.ambiguous:
            note = "date-only change on ride day"
        elif ride.assignment_uncertain:
            note = "ride marked uncertain"
        if in_baseline:
            note = "before starting-mileage date (inside starting value)"
        session.add(UsageContribution(
            ride_id=ride.id, component_id=u.component_id, bike_id=ride.bike_id, slot=u.slot, sort_utc=ride.sort_utc,
            km=km, duration_s=ride.duration_s, basis=u.basis, certain=certain,
            state="IN_BASELINE" if in_baseline else "COUNTED", note=note,
        ))
    for code, slot, detail in flags:
        session.add(RideFlag(ride_id=ride.id, code=code, slot=slot, detail=detail))
    session.flush()


def allocate_rides(session: Session, rides: list[Ride], tz: str) -> None:
    index = AllocationIndex(session, tz)
    for r in rides:
        allocate_ride(session, r, index)


def rebuild_all(session: Session, tz: str) -> int:
    """Recompute every contribution from scratch. Deterministic: running it twice changes nothing."""
    rides = list(session.scalars(select(Ride).order_by(Ride.id)))
    allocate_rides(session, rides, tz)
    return len(rides)
