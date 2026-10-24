"""Small builders for tests. They call the real services; nothing is mocked."""
from __future__ import annotations

from bikelog.services import inventory as inv
from bikelog.services import rides
from bikelog.services.usage import component_usage


def bike(session, name="TIME NXR", **kw):
    return inv.create_bike(session, name=name, **kw)


def part(session, ctype, label, **kw):
    kw.setdefault("prior_usage", "NEW")
    return inv.create_component(session, component_type=ctype, label=label, **kw)


def ride(session, bike_obj, when, km, **kw):
    return rides.add_manual_ride(session, bike_id=bike_obj.id if bike_obj else None, when=when, distance=km, **kw)


def km(session, comp) -> float:
    session.flush()
    return component_usage(session, comp)["total_km"]
