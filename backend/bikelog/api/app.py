"""FastAPI application: JSON under /api, the built frontend at /.

The API only translates HTTP to service calls. Every mutation runs in one short transaction,
accepts an optional X-Client-Op-Id header (a repeat returns the first result) and, where mileage
can change, ?dry_run=true to preview the impact without saving.
"""
from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, object_session, sessionmaker

from bikelog import __version__, backup, buildinfo, changelog
from bikelog.api.security import LocalSecurityMiddleware
from bikelog.catalog import (
    ACTIONS, COMPONENT_TYPES, DISPOSITIONS, INCIDENT_TYPES, RIDE_CONDITIONS, SHIFTING_TYPES, TIRE_SETUPS, TRACKING_MODES,
    action_applies,
)
from bikelog.connectors.strava import sync as strava
from bikelog.migrate import head_revision
from bikelog.models import Bike, Component, Product, ServiceRule, UsageProfile
from bikelog.paths import DataPaths, resource_root
from bikelog.services import costs as costs_svc
from bikelog.services import bundles as bundles_svc
from bikelog.services import demo, diagnostics, groupsets, imports, journal, product_import, spares, stock
from bikelog.services import worksessions as ws_svc
from bikelog.services import inventory as inv
from bikelog.services import maintenance as m
from bikelog.services import rides as rides_svc
from bikelog.services import settings as settings_svc
from bikelog.services.errors import DomainError
from bikelog.services.operations import run_once, with_change
from bikelog.services.rebuild import rebuild_everything
from bikelog.services.usage import bike_usage, component_ledger, component_usage

log = logging.getLogger(__name__)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- request bodies

class BikeIn(Body):
    name: str
    maker: str | None = None
    model: str | None = None
    year: int | None = None
    strava_gear_id: str | None = None
    notes: str | None = None
    starting_km: float | None = None
    starting_date: str | None = None
    starting_is_estimate: bool = False
    purchase_price_cents: int | None = None
    purchase_date: str | None = None
    shifting: str | None = None


class BikePatch(Body):
    name: str | None = None
    maker: str | None = None
    model: str | None = None
    year: int | None = None
    strava_gear_id: str | None = None
    notes: str | None = None
    purchase_price_cents: int | None = None
    purchase_date: str | None = None
    shifting: str | None = None


class StartingIn(Body):
    km: float
    effective: str | None = None
    is_estimate: bool = False
    note: str | None = None


class ProductIn(Body):
    component_type: str
    model: str
    maker: str | None = None
    specs: dict | None = None
    spec_source: str | None = None
    spec_version: str | None = None
    notes: str | None = None
    list_price_cents: int | None = None


class ProductPatch(Body):
    maker: str | None = None
    model: str | None = None
    notes: str | None = None
    list_price_cents: int | None = None


class InstallIn(Body):
    at: str
    bike_id: int | None = None
    parent_component_id: int | None = None
    slot: str | None = None
    until: str | None = None
    note: str | None = None


class ComponentIn(Body):
    component_type: str
    label: str
    product_id: int | None = None
    prior_usage: str = "UNKNOWN"
    serial_number: str | None = None
    purchase_date: str | None = None
    price_cents: int | None = None
    notes: str | None = None
    specs: dict | None = None
    starting_km: float | None = None
    starting_date: str | None = None
    starting_is_estimate: bool = False
    storage_location: str | None = None
    tire_setup: str | None = None
    install: InstallIn | None = None


class ComponentPatch(Body):
    label: str | None = None
    serial_number: str | None = None
    purchase_date: str | None = None
    price_cents: int | None = None
    notes: str | None = None
    product_id: int | None = None
    prior_usage: str | None = None
    specs: dict | None = None
    storage_location: str | None = None
    tire_setup: str | None = None


class RemoveIn(Body):
    at: str
    reason: str | None = None
    outcome: str | None = None


class NewItemIn(Body):
    label: str | None = None
    product_id: int | None = None
    price_cents: int | None = None
    purchase_date: str | None = None
    prior_usage: str | None = None
    notes: str | None = None


class ReplaceIn(Body):
    at: str
    new_component_id: int | None = None
    same_product: bool = False
    from_stock_id: int | None = None
    new: NewItemIn | None = None
    new_label: str | None = None
    reason: str | None = None
    old_outcome: str | None = None
    carry_over: list[int] | None = None
    session_notes: str | None = None


class GroupWheelsIn(Body):
    at: str
    label: str | None = None
    wheelset_id: int | None = None


class MoveIn(Body):
    at: str
    bike_id: int | None = None
    parent_component_id: int | None = None
    slot: str | None = None
    swap: bool = False
    reason: str | None = None


class DispositionIn(Body):
    disposition: str
    on: str
    note: str | None = None


class RetireIn(Body):
    on: str
    reason: str | None = None
    disposition: str = "RETIRED"


class StockInstallIn(Body):
    at: str
    bike_id: int | None = None
    parent_component_id: int | None = None
    slot: str | None = None
    label: str | None = None


class CompatIn(Body):
    bike_id: int
    verified: bool = False
    note: str | None = None


class GroupsetPlanIn(Body):
    bike_id: int | None = None
    options: dict[str, str] = {}
    include: list[str] | None = None
    label_prefix: str | None = None
    occupied: str = "KEEP"
    to_spares: list[str] = []


class BundlePriceIn(Body):
    name: str | None = None
    merchant: str | None = None
    purchased_on: str | None = None
    price_cents: int | None = None
    notes: str | None = None


class BundleIn(Body):
    name: str
    component_ids: list[int]
    merchant: str | None = None
    purchased_on: str | None = None
    price_cents: int | None = None
    notes: str | None = None


class BundlePatch(Body):
    name: str | None = None
    merchant: str | None = None
    purchased_on: str | None = None
    price_cents: int | None = None
    notes: str | None = None


class BundleMembersIn(Body):
    component_ids: list[int]


class GroupsetImportIn(GroupsetPlanIn):
    at: str
    prices: dict[str, int] = {}
    prior_usage: str = "NEW"
    purchase_date: str | None = None
    outcomes: dict[str, str] = {}
    notes: str | None = None
    bundle: BundlePriceIn | None = None


class StravaCredentialsIn(Body):
    client_id: str
    client_secret: str | None = None


class StravaSyncIn(Body):
    rescan: bool = False


class AssignBikeIn(Body):
    ride_ids: list[int]
    bike_id: int | None = None


class JournalIn(Body):
    text: str | None = None
    on: str | None = None
    bike_id: int | None = None
    component_id: int | None = None
    kind: str | None = None
    resolved_on: str | None = None
    ride_id: int | None = None
    incident_type: str | None = None


class JournalPatch(Body):
    text: str | None = None
    on: str | None = None
    kind: str | None = None
    resolved_on: str | None = None
    incident_type: str | None = None


class UndoIn(Body):
    reason: str | None = None


class CorrectionIn(Body):
    km: float
    effective: str
    note: str


class ResetIn(Body):
    confirm: str
    clear_strava: bool = False


class VoidIn(Body):
    reason: str


class InstallCorrectIn(Body):
    installed_at: str | None = None
    removed_at: str | None = None
    clear_removed: bool = False
    reason: str


class RideIn(Body):
    bike_id: int | None = None
    when: str
    distance: float | None = None
    unit: str = "km"
    duration_s: int | None = None
    name: str | None = None
    sport_type: str = "Ride"
    usage_profile_code: str | None = None
    assignment_uncertain: bool = False
    uncertainty_note: str | None = None
    notes: str | None = None
    conditions: str | None = None
    equipment: dict[str, int | None] | None = None


class RidePatch(Body):
    name: str | None = None
    when: str | None = None
    distance_km: float | None = None
    unit: str | None = None
    duration_s: int | None = None
    bike_id: int | None = None
    sport_type: str | None = None
    usage_profile_code: str | None = None
    assignment_uncertain: bool | None = None
    uncertainty_note: str | None = None
    notes: str | None = None
    conditions: str | None = None


class ExcludeIn(Body):
    reason: str | None = None


class EquipmentIn(Body):
    component_id: int | None = None
    note: str | None = None


class EventIn(Body):
    action_code: str
    at: str
    component_id: int | None = None
    component_ids: list[int] | None = None
    bike_id: int | None = None
    symptom: str | None = None
    work_done: str | None = None
    outcome: str | None = None
    measurement_value: float | None = None
    measurement_unit: str | None = None
    consumable_id: int | None = None
    consumable_qty: float | None = None
    cost_cents: int | None = None
    notes: str | None = None
    disposition_after: str | None = None


class SnoozeIn(Body):
    component_id: int | None = None
    bike_id: int | None = None          # bike-level reminder (component_id empty)
    rule_code: str
    until_date: str | None = None
    extra_km: float | None = None
    note: str | None = None


class RulePatch(Body):
    name: str | None = None
    interval_km: float | None = None
    interval_months: int | None = None
    window_min_km: float | None = None
    window_max_km: float | None = None
    warn_km: float | None = None
    warn_days: int | None = None
    active: bool | None = None
    origin: str | None = None
    notes: str | None = None
    interval_hours: float | None = None
    warn_hours: float | None = None
    interval_count: int | None = None


class ComponentRuleIn(RulePatch):
    rule_code: str | None = None
    action_code: str | None = None


class ConsumableIn(Body):
    kind: str = "OTHER"
    name: str | None = None
    maker: str | None = None
    unit: str | None = None
    track_stock: bool = False
    notes: str | None = None
    tracking_mode: str = "BULK"
    component_type: str | None = None
    product_id: int | None = None
    unit_note: str | None = None
    storage_location: str | None = None
    min_stock: float | None = None
    container_size: float | None = None


class ConsumablePatch(Body):
    name: str | None = None
    maker: str | None = None
    unit: str | None = None
    unit_note: str | None = None
    storage_location: str | None = None
    min_stock: float | None = None
    container_size: float | None = None
    notes: str | None = None


class TxnIn(Body):
    kind: str
    qty: float | None = None
    on: str
    cost_cents: int | None = None
    note: str | None = None
    packages: int | None = None


class SettingsPatch(Body):
    timezone: str | None = None
    import_start_date: str | None = None
    trainer_profile_for_virtual: str | None = None
    default_tire_setup: str | None = None


class ProfileIn(Body):
    code: str
    name: str
    excluded_slots: list[str] = []
    excluded_types: list[str] = []
    notes: str | None = None


# ---------------------------------------------------------------- app

def create_app(factory: sessionmaker[Session], paths: DataPaths, *, token: str | None = None,
               static_dir: Path | None = None, testing: bool = False, strava_transport=None) -> FastAPI:
    token = token or secrets.token_urlsafe(32)
    app = FastAPI(title="Bike Log", version=__version__, docs_url="/api/docs" if testing else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if testing else None)
    app.state.token = token
    static = static_dir if static_dir is not None else _find_static()
    app.add_middleware(LocalSecurityMiddleware, token=token, allow_test_host=testing)
    from bikelog.connectors.strava.client import urllib_transport
    from bikelog.connectors.strava.web import StravaWeb
    strava_web = StravaWeb(paths, factory, transport=strava_transport or urllib_transport)
    app.state.strava = strava_web

    def db() -> Iterator[Session]:
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @app.exception_handler(DomainError)
    async def _domain(req: Request, exc: DomainError):
        log.info("refused %s %s: %s", req.method, req.url.path, exc.message)
        return JSONResponse({"detail": exc.message, **exc.details}, status_code=exc.status)

    @app.exception_handler(IntegrityError)
    async def _integrity(_req: Request, exc: IntegrityError):
        msg = str(exc.orig)
        status = 409 if ("CONFLICT" in msg or "PROTECTED" in msg or "UNIQUE" in msg) else 400
        return JSONResponse({"detail": f"Rejected by the database: {msg}"}, status_code=status)

    @app.exception_handler(Exception)
    async def _unexpected(req: Request, exc: Exception):
        log.error("unexpected error in %s %s", req.method, req.url.path, exc_info=exc)
        return JSONResponse({"detail": "Something went wrong inside Bike Log. Nothing was saved. The details are "
                                       "in the log (Settings → Diagnostics)."}, status_code=500)

    @app.exception_handler(OperationalError)
    async def _busy(_req: Request, exc: OperationalError):
        log.warning("database error: %s", exc)
        return JSONResponse({"detail": "The database is busy or unavailable. Try again in a moment."},
                            status_code=503)

    def op(s: Session, op_id: str | None, kind: str, fn: Callable[[], Any], dry_run: bool = False) -> dict:
        def run() -> dict:
            result, change = with_change(s, fn, dry_run=dry_run)
            return {"result": result, "change": change}
        token = changelog.set_via(kind)
        try:
            res = run_once(s, op_id, kind, run)
            if not (dry_run or res.get("repeated")):
                log.info("%s done%s", kind, f": {res['change']['notice']}" if (res.get("change") or {}).get("notice") else "")
            return res
        finally:
            changelog.reset(token)

    OpId = Header(default=None, alias="X-Client-Op-Id")

    # ------------------------------------------------------------ meta

    @app.get("/api/health")
    def health(s: Session = Depends(db)):
        return {"ok": True, "version": __version__, "full_version": buildinfo.full_version(),
                "release": buildinfo.is_release(), "schema": head_revision(), "demo": demo.is_demo(s),
                "commit": buildinfo.commit(), "ui_commit": buildinfo.ui_commit(static)}

    @app.get("/api/meta")
    def meta(s: Session = Depends(db)):
        return {
            "version": __version__, "demo": demo.is_demo(s), "safety_note": m.SAFETY_NOTE,
            "schema": head_revision(), "commit": buildinfo.commit(), "ui_commit": buildinfo.ui_commit(static),
            "full_version": buildinfo.full_version(), "release": buildinfo.is_release(),
            "ui_version": buildinfo.ui_version(static),
            "settings": settings_svc.all_settings(s),
            "component_types": [{"code": t.code, "name": t.name, "category": t.category, "slots": list(t.slots),
                                 "parent_types": list(t.parent_types), "removed_default": t.removed_default,
                                 "rider_gear": t.rider_gear, "torque": t.torque}
                                for t in COMPONENT_TYPES.values()],
            "dispositions": [{"code": k, "label": v} for k, v in DISPOSITIONS.items()],
            "tracking_modes": [{"code": k, "label": v} for k, v in TRACKING_MODES.items()],
            "tire_setups": [{"code": k, "label": v} for k, v in TIRE_SETUPS.items()],
            "shifting_types": [{"code": k, "label": v} for k, v in SHIFTING_TYPES.items()],
            "incident_types": [{"code": k, "label": v} for k, v in INCIDENT_TYPES.items()],
            "ride_conditions": [{"code": k, "label": v} for k, v in RIDE_CONDITIONS.items()],
            "actions": [{"code": a.code, "name": a.name, "kind": a.kind, "targets": list(a.targets),
                         "quick": a.quick, "fields": list(a.fields), "outcomes": list(a.outcomes),
                         "unit": a.unit, "limits_source": a.limits_source,
                         "limits": [{"value": x.value, "outcome": x.outcome, "below": x.below} for x in a.limits]}
                        for a in ACTIONS.values()],
            "profiles": [{"id": p.id, "code": p.code, "name": p.name, "kind": p.kind,
                          "excluded_slots": json.loads(p.excluded_slots_json),
                          "excluded_types": json.loads(p.excluded_types_json), "notes": p.notes}
                         for p in s.scalars(select(UsageProfile).order_by(UsageProfile.id))],
        }

    # ------------------------------------------------------------ overview

    @app.get("/api/overview")
    def overview(s: Session = Depends(db)):
        bikes = [_bike_summary(s, b) for b in s.scalars(select(Bike).order_by(Bike.status, Bike.name))]
        recent = rides_svc.list_rides(s, limit=8)
        flagged = [r for r in rides_svc.list_rides(s, limit=500, flagged_only=True) if r["inclusion"] == "INCLUDED"]
        return {"bikes": bikes, "queue": m.queue(s), "chains": m.chain_overview(s), "brakes": m.brake_overview(s),
                "recent_rides": recent, "flagged_rides": flagged[:20], "flagged_count": len(flagged),
                "safety_note": m.SAFETY_NOTE, "demo": demo.is_demo(s)}

    # ------------------------------------------------------------ bikes

    @app.get("/api/bikes")
    def bikes(s: Session = Depends(db)):
        attribution = costs_svc.bike_attribution(s)
        return [_bike_summary(s, b, attribution) for b in s.scalars(select(Bike).order_by(Bike.status, Bike.name))]

    @app.post("/api/bikes", status_code=201)
    def create_bike(body: BikeIn, s: Session = Depends(db), op_id: str | None = OpId):
        return run_once(s, op_id, "bike.create", lambda: _bike_summary(s, inv.create_bike(s, **body.model_dump())))

    @app.get("/api/bikes/{bike_id}")
    def bike_detail(bike_id: int, s: Session = Depends(db)):
        b = inv.get_bike(s, bike_id)
        return {**_bike_summary(s, b), "setup": inv.bike_setup(s, b), "history": inv.bike_installation_history(s, b),
                "queue": m.queue(s, bike_id=b.id, include_ok=True), "brakes": m.brake_overview(s, bike_id=b.id),
                "rides": rides_svc.list_rides(s, bike_id=b.id, limit=20),
                "events": m.events_for(s, bike_id=b.id, limit=20),
                "cost_detail": costs_svc.bike_costs(s, b)}

    @app.patch("/api/bikes/{bike_id}")
    def patch_bike(bike_id: int, body: BikePatch, s: Session = Depends(db)):
        return _bike_summary(s, inv.update_bike(s, bike_id, **body.model_dump(exclude_unset=True)))

    @app.post("/api/bikes/{bike_id}/retire")
    def retire_bike(bike_id: int, s: Session = Depends(db)):
        return _bike_summary(s, inv.retire_bike(s, bike_id))

    @app.post("/api/bikes/{bike_id}/starting-usage")
    def bike_start(bike_id: int, body: StartingIn, s: Session = Depends(db)):
        inv.get_bike(s, bike_id)
        inv.set_starting_usage(s, bike_id=bike_id, km=body.km, effective=body.effective,
                               is_estimate=body.is_estimate, note=body.note)
        return _bike_summary(s, inv.get_bike(s, bike_id))

    @app.post("/api/bikes/{bike_id}/group-wheels")
    def bike_group_wheels(bike_id: int, body: GroupWheelsIn, dry_run: bool = False, s: Session = Depends(db),
                          op_id: str | None = OpId):
        def fn():
            ws = ws_svc.begin(s, at=body.at, bike_id=bike_id, title="Group wheels into a wheelset")
            return {**inv.group_wheels(s, bike_id, at=body.at, label=body.label, wheelset_id=body.wheelset_id,
                                       work_session_id=ws.id), "work_session_id": ws.id}
        return op(s, op_id, "bike.group_wheels", fn, dry_run)

    # ------------------------------------------------------------ products & components

    @app.get("/api/products")
    def products(component_type: str | None = None, s: Session = Depends(db)):
        q = select(Product).order_by(Product.maker, Product.model)
        if component_type:
            q = q.where(Product.component_type == component_type)
        return [_product(p) for p in s.scalars(q)]

    @app.post("/api/products", status_code=201)
    def create_product(body: ProductIn, s: Session = Depends(db)):
        return _product(inv.create_product(s, **body.model_dump()))

    @app.patch("/api/products/{product_id}")
    def patch_product(product_id: int, body: ProductPatch, s: Session = Depends(db)):
        return _product(inv.update_product(s, product_id, **body.model_dump(exclude_unset=True)))

    @app.get("/api/components")
    def components(state: str | None = None, component_type: str | None = None, s: Session = Depends(db)):
        q = select(Component).order_by(Component.component_type, Component.label)
        if component_type:
            q = q.where(Component.component_type == component_type)
        rows = [_component_summary(s, c) for c in s.scalars(q)]
        if state:
            rows = [r for r in rows if r["location"]["state"] == state]
        return rows

    @app.post("/api/components", status_code=201)
    def create_component(body: ComponentIn, s: Session = Depends(db), op_id: str | None = OpId):
        data = body.model_dump(exclude={"install"})

        def fn():
            c = inv.create_component(s, **data)
            if body.install:
                inv.install(s, c.id, **body.install.model_dump())
            return _component_summary(s, c)
        return run_once(s, op_id, "component.create", fn)

    @app.get("/api/components/{component_id}")
    def component_detail(component_id: int, s: Session = Depends(db)):
        c = inv.get_component(s, component_id)
        return {**_component_summary(s, c), "ledger": component_ledger(s, c),
                "history": inv.installation_history(s, c), "service_status": m.component_status(s, c),
                "rules": [m.rule_row(r) for r in m.effective_rules(s, c, include_disabled=True)],
                "events": m.events_for(s, component_id=c.id),
                "actions": [{"code": a.code, "name": a.name, "quick": a.quick, "fields": list(a.fields),
                             "outcomes": list(a.outcomes), "unit": a.unit, "limits_source": a.limits_source}
                            for a in ACTIONS.values() if action_applies(a, c.component_type)],
                "product_detail": _product(c.product) if c.product else None, "specs": json.loads(c.specs_json or "{}"),
                "dispositions": inv.disposition_history(s, c), "inventory": spares.item_row(s, c),
                "suggested_outcome": COMPONENT_TYPES[c.component_type].removed_default}

    @app.patch("/api/components/{component_id}")
    def patch_component(component_id: int, body: ComponentPatch, s: Session = Depends(db)):
        return _component_summary(s, inv.update_component(s, component_id, **body.model_dump(exclude_unset=True)))

    @app.delete("/api/components/{component_id}")
    def delete_component(component_id: int, s: Session = Depends(db)):
        inv.delete_component(s, component_id)
        return {"deleted": component_id}

    @app.post("/api/components/{component_id}/install")
    def install(component_id: int, body: InstallIn, dry_run: bool = False, s: Session = Depends(db),
                op_id: str | None = OpId):
        def fn():
            ws = ws_svc.begin(s, at=body.at, bike_id=body.bike_id, title="Install")
            inst = inv.install(s, component_id, work_session_id=ws.id, **body.model_dump())
            return {"installation_id": inst.id, "work_session_id": ws.id}
        return op(s, op_id, "component.install", fn, dry_run)

    @app.post("/api/components/{component_id}/remove")
    def remove(component_id: int, body: RemoveIn, dry_run: bool = False, s: Session = Depends(db),
               op_id: str | None = OpId):
        def fn():
            loc = inv.location(s, inv.get_component(s, component_id))
            ws = ws_svc.begin(s, at=body.at, bike_id=loc.get("bike_id"), title="Remove")
            inst = inv.remove(s, component_id, work_session_id=ws.id, **body.model_dump())
            return {"installation_id": inst.id, "work_session_id": ws.id}
        return op(s, op_id, "component.remove", fn, dry_run)

    @app.get("/api/components/{component_id}/replace-options")
    def replace_options(component_id: int, s: Session = Depends(db)):
        return spares.replace_options(s, component_id)

    @app.post("/api/components/{component_id}/replace")
    def replace(component_id: int, body: ReplaceIn, dry_run: bool = False, s: Session = Depends(db),
                op_id: str | None = OpId):
        data = body.model_dump(exclude={"session_notes", "new"})
        if body.new is not None:
            data["new"] = body.new.model_dump(exclude_none=True)

        def fn():
            comp = inv.get_component(s, component_id)
            loc = inv.location(s, comp)
            ws = ws_svc.begin(s, at=body.at, bike_id=loc.get("bike_id"), title=f"Replace {comp.label}",
                              notes=body.session_notes)
            return {**inv.replace(s, component_id, work_session_id=ws.id, **data), "work_session_id": ws.id}
        return op(s, op_id, "component.replace", fn, dry_run)

    @app.get("/api/components/{component_id}/move-targets")
    def move_targets(component_id: int, s: Session = Depends(db)):
        return spares.move_targets(s, component_id)

    @app.post("/api/components/{component_id}/move")
    def move(component_id: int, body: MoveIn, dry_run: bool = False, s: Session = Depends(db),
             op_id: str | None = OpId):
        def fn():
            comp = inv.get_component(s, component_id)
            ws = ws_svc.begin(s, at=body.at, bike_id=inv.location(s, comp).get("bike_id"), title=f"Move {comp.label}")
            return {**inv.move(s, component_id, work_session_id=ws.id, **body.model_dump()), "work_session_id": ws.id}
        return op(s, op_id, "component.move", fn, dry_run)

    @app.post("/api/components/{component_id}/disposition")
    def disposition(component_id: int, body: DispositionIn, s: Session = Depends(db), op_id: str | None = OpId):
        def fn():
            ws = ws_svc.begin(s, at=body.on, title="Inventory update")
            inv.set_disposition(s, component_id, body.disposition, on=body.on, note=body.note, work_session_id=ws.id)
            return {**_component_summary(s, inv.get_component(s, component_id)), "work_session_id": ws.id}
        return op(s, op_id, "component.disposition", fn)

    @app.post("/api/components/{component_id}/retire")
    def retire(component_id: int, body: RetireIn, s: Session = Depends(db)):
        ws = ws_svc.begin(s, at=body.on, title="Retire")
        return _component_summary(s, inv.retire_component(s, component_id, work_session_id=ws.id, **body.model_dump()))

    @app.post("/api/components/{component_id}/starting-usage")
    def comp_start(component_id: int, body: StartingIn, dry_run: bool = False, s: Session = Depends(db)):
        return op(s, None, "component.starting", lambda: {"id": inv.set_starting_usage(
            s, component_id=component_id, km=body.km, effective=body.effective, is_estimate=body.is_estimate,
            note=body.note).id}, dry_run)

    @app.post("/api/components/{component_id}/correction")
    def comp_correction(component_id: int, body: CorrectionIn, dry_run: bool = False, s: Session = Depends(db)):
        inv.get_component(s, component_id)
        return op(s, None, "component.correction",
                  lambda: {"id": inv.add_correction(s, component_id, **body.model_dump()).id}, dry_run)

    @app.post("/api/components/{component_id}/rules", status_code=201)
    def comp_rule(component_id: int, body: ComponentRuleIn, s: Session = Depends(db)):
        data = body.model_dump(exclude_unset=True)
        return m.rule_row(m.set_component_rule(s, component_id, **data))

    @app.post("/api/installations/{installation_id}/void")
    def void_installation(installation_id: int, body: VoidIn, dry_run: bool = False, s: Session = Depends(db)):
        return op(s, None, "installation.void",
                  lambda: {"id": inv.void_installation(s, installation_id, body.reason).id}, dry_run)

    @app.post("/api/installations/{installation_id}/correct")
    def correct_installation(installation_id: int, body: InstallCorrectIn, dry_run: bool = False,
                             s: Session = Depends(db)):
        return op(s, None, "installation.correct",
                  lambda: {"id": inv.correct_installation(s, installation_id, **body.model_dump()).id}, dry_run)

    # ------------------------------------------------------------ rides

    @app.get("/api/rides")
    def list_rides(bike_id: int | None = None, flagged: bool = False, include_excluded: bool = True,
                   view: str = "all", unassigned: bool = False,
                   limit: int = Query(200, le=1000), offset: int = 0, s: Session = Depends(db)):
        if view not in ("all", "active", "removed"):
            raise DomainError("view must be all, active or removed")
        rows = rides_svc.list_rides(s, bike_id=bike_id, flagged_only=flagged, include_excluded=include_excluded,
                                    limit=limit, offset=offset, view=view, unassigned=unassigned)
        return rows

    @app.post("/api/rides/assign-bike")
    def assign_bike(body: AssignBikeIn, dry_run: bool = False, s: Session = Depends(db), op_id: str | None = OpId):
        return op(s, op_id, "ride.assign_bike", lambda: rides_svc.assign_bike(s, body.ride_ids, body.bike_id), dry_run)

    @app.post("/api/rides", status_code=201)
    def add_ride(body: RideIn, s: Session = Depends(db), op_id: str | None = OpId):
        return op(s, op_id, "ride.add", lambda: rides_svc.ride_row(s, rides_svc.add_manual_ride(s, **body.model_dump())))

    @app.get("/api/rides/{ride_id}")
    def ride_detail(ride_id: int, s: Session = Depends(db)):
        return rides_svc.ride_detail(s, rides_svc.get_ride(s, ride_id))

    @app.patch("/api/rides/{ride_id}")
    def edit_ride(ride_id: int, body: RidePatch, dry_run: bool = False, s: Session = Depends(db),
                  op_id: str | None = OpId):
        changes = body.model_dump(exclude_unset=True)
        return op(s, op_id, "ride.edit", lambda: rides_svc.ride_row(s, rides_svc.edit_ride(s, ride_id, changes)), dry_run)

    @app.post("/api/rides/{ride_id}/exclude")
    def exclude(ride_id: int, body: ExcludeIn, dry_run: bool = False, s: Session = Depends(db),
                op_id: str | None = OpId):
        return op(s, op_id, "ride.exclude",
                  lambda: rides_svc.ride_row(s, rides_svc.exclude_ride(s, ride_id, body.reason)), dry_run)

    @app.post("/api/rides/{ride_id}/restore")
    def restore(ride_id: int, dry_run: bool = False, s: Session = Depends(db), op_id: str | None = OpId):
        return op(s, op_id, "ride.restore", lambda: rides_svc.ride_row(s, rides_svc.restore_ride(s, ride_id)), dry_run)

    @app.put("/api/rides/{ride_id}/equipment/{slot}")
    def set_equipment(ride_id: int, slot: str, body: EquipmentIn, dry_run: bool = False, s: Session = Depends(db)):
        return op(s, None, "ride.equipment", lambda: rides_svc.ride_detail(
            s, rides_svc.set_equipment(s, ride_id, slot, body.component_id, body.note)), dry_run)

    @app.delete("/api/rides/{ride_id}/equipment/{slot}")
    def clear_equipment(ride_id: int, slot: str, dry_run: bool = False, s: Session = Depends(db)):
        return op(s, None, "ride.equipment.clear",
                  lambda: rides_svc.ride_detail(s, rides_svc.clear_equipment(s, ride_id, slot)), dry_run)

    # ------------------------------------------------------------ maintenance

    @app.get("/api/maintenance/queue")
    def queue(bike_id: int | None = None, include_ok: bool = False, s: Session = Depends(db)):
        return m.queue(s, bike_id=bike_id, include_ok=include_ok)

    @app.get("/api/maintenance/events")
    def events(component_id: int | None = None, bike_id: int | None = None, limit: int = 200,
               s: Session = Depends(db)):
        return m.events_for(s, component_id=component_id, bike_id=bike_id, limit=limit)

    @app.get("/api/maintenance/candidates")
    def candidates(bike_id: int, action_code: str, s: Session = Depends(db)):
        return m.installed_parts_for_action(s, bike_id, action_code)

    @app.post("/api/maintenance/events", status_code=201)
    def log_event(body: EventIn, s: Session = Depends(db), op_id: str | None = OpId):
        data = body.model_dump(exclude={"component_ids"})

        def fn():
            ws = ws_svc.begin(s, at=body.at, bike_id=body.bike_id, title=ACTIONS.get(body.action_code).name
                              if body.action_code in ACTIONS else None)
            if body.component_ids:
                data.pop("component_id")
                data.pop("bike_id")
                evs = m.log_batch(s, component_ids=body.component_ids, work_session_id=ws.id, **data)
            else:
                evs = [m.log_event(s, work_session_id=ws.id, **data)]
            ids = [e.id for e in evs]
            return {"event_ids": ids, "work_session_id": ws.id,
                    "status": [m.component_status(s, inv.get_component(s, e.component_id))
                               for e in evs if e.component_id]}
        return run_once(s, op_id, "maintenance.log", fn)

    @app.post("/api/maintenance/events/{event_id}/void")
    def void_event(event_id: int, body: VoidIn, s: Session = Depends(db)):
        e = m.void_event(s, event_id, body.reason)
        return {"id": e.id, "voided": True}

    @app.post("/api/maintenance/snooze", status_code=201)
    def snooze(body: SnoozeIn, s: Session = Depends(db)):
        sn = m.snooze(s, **body.model_dump())
        return {"id": sn.id, "until_date": sn.until_date, "until_km": sn.until_km}

    @app.delete("/api/maintenance/snooze/{snooze_id}")
    def unsnooze(snooze_id: int, s: Session = Depends(db)):
        m.unsnooze(s, snooze_id)
        return {"id": snooze_id, "cleared": True}

    @app.get("/api/rules")
    def rules(s: Session = Depends(db)):
        return [m.rule_row(r) for r in s.scalars(select(ServiceRule).where(ServiceRule.component_type.is_not(None))
                                                 .order_by(ServiceRule.component_type, ServiceRule.rule_code))]

    @app.get("/api/bikes/{bike_id}/rules")
    def bike_rules(bike_id: int, s: Session = Depends(db)):
        b = inv.get_bike(s, bike_id)
        return [{**m.rule_row(r), "status": m.bike_rule_status(s, b, r)}
                for r in m.effective_bike_rules(s, b, include_disabled=True)]

    @app.patch("/api/bikes/{bike_id}/rules/{rule_code}")
    def patch_bike_rule(bike_id: int, rule_code: str, body: RulePatch, s: Session = Depends(db)):
        return m.rule_row(m.set_bike_rule(s, bike_id, rule_code, **body.model_dump(exclude_unset=True)))

    @app.patch("/api/rules/{rule_id}")
    def patch_rule(rule_id: int, body: RulePatch, s: Session = Depends(db)):
        return m.rule_row(m.update_rule(s, rule_id, **body.model_dump(exclude_unset=True)))

    @app.get("/api/chains")
    def chains(s: Session = Depends(db)):
        return m.chain_overview(s)

    @app.get("/api/brakes")
    def brakes(bike_id: int | None = None, s: Session = Depends(db)):
        return m.brake_overview(s, bike_id=bike_id)

    @app.get("/api/consumables")
    def consumables(s: Session = Depends(db)):
        return m.consumable_stock(s)

    @app.post("/api/consumables", status_code=201)
    def add_consumable(body: ConsumableIn, s: Session = Depends(db), op_id: str | None = OpId):
        def fn():
            c = stock.add_consumable(s, **body.model_dump())
            return {"id": c.id, "name": c.name, "unit": c.unit, "unit_note": c.unit_note}
        return run_once(s, op_id, "stock.create", fn)

    @app.patch("/api/consumables/{consumable_id}")
    def patch_consumable(consumable_id: int, body: ConsumablePatch, s: Session = Depends(db)):
        c = stock.update_consumable(s, consumable_id, **body.model_dump(exclude_unset=True))
        return {"id": c.id, "name": c.name}

    @app.get("/api/consumables/{consumable_id}/txns")
    def consumable_txns(consumable_id: int, s: Session = Depends(db)):
        return stock.txn_history(s, consumable_id)

    @app.post("/api/consumables/{consumable_id}/txn", status_code=201)
    def consumable_txn(consumable_id: int, body: TxnIn, s: Session = Depends(db), op_id: str | None = OpId):
        def fn():
            ws = ws_svc.begin(s, at=body.on, title={"PURCHASE": "Purchase", "RETURN": "Return to shop",
                                                   "ADJUST": "Stock correction", "USE": "Used supplies"}
                              .get(body.kind, "Stock"))
            t = stock.consumable_txn(s, consumable_id, work_session_id=ws.id, **body.model_dump())
            return {"id": t.id, "work_session_id": ws.id}
        return run_once(s, op_id, "stock.txn", fn)

    @app.post("/api/consumables/{consumable_id}/install")
    def install_from_stock(consumable_id: int, body: StockInstallIn, dry_run: bool = False,
                           s: Session = Depends(db), op_id: str | None = OpId):
        def fn():
            ws = ws_svc.begin(s, at=body.at, bike_id=body.bike_id, title="Install from stock")
            comp = stock.draw_component(s, consumable_id, on=body.at, label=body.label, work_session_id=ws.id)
            inst = inv.install(s, comp.id, at=body.at, bike_id=body.bike_id,
                               parent_component_id=body.parent_component_id, slot=body.slot, work_session_id=ws.id)
            return {"component_id": comp.id, "label": comp.label, "installation_id": inst.id, "work_session_id": ws.id}
        return op(s, op_id, "stock.install", fn, dry_run)

    @app.get("/api/inventory")
    def inventory_view(s: Session = Depends(db)):
        return spares.inventory(s)

    @app.get("/api/shopping-list")
    def shopping_list(s: Session = Depends(db)):
        return stock.shopping_list(s)

    @app.post("/api/products/{product_id}/compatibility")
    def product_compat(product_id: int, body: CompatIn, s: Session = Depends(db)):
        if not s.get(Product, product_id):
            raise DomainError("Product not found")
        inv.get_bike(s, body.bike_id)
        return spares.set_compatibility(s, product_id, body.bike_id, body.verified, body.note)

    @app.get("/api/journal")
    def journal_list(bike_id: int | None = None, component_id: int | None = None, ride_id: int | None = None,
                     include_voided: bool = False, s: Session = Depends(db)):
        return journal.entries(s, bike_id=bike_id, component_id=component_id, ride_id=ride_id,
                               include_voided=include_voided)

    @app.get("/api/incidents")
    def incident_list(bike_id: int | None = None, component_id: int | None = None, incident_type: str | None = None,
                      open_only: bool = False, s: Session = Depends(db)):
        return journal.incidents(s, bike_id=bike_id, component_id=component_id, incident_type=incident_type,
                                 open_only=open_only)

    @app.post("/api/journal", status_code=201)
    def journal_add(body: JournalIn, s: Session = Depends(db), op_id: str | None = OpId):
        return run_once(s, op_id, "journal.add", lambda: journal.row(s, journal.add(s, **body.model_dump())))

    @app.patch("/api/journal/{entry_id}")
    def journal_edit(entry_id: int, body: JournalPatch, s: Session = Depends(db)):
        return journal.row(s, journal.update(s, entry_id, **body.model_dump(exclude_unset=True)))

    @app.post("/api/journal/{entry_id}/void")
    def journal_void(entry_id: int, body: VoidIn, s: Session = Depends(db)):
        return journal.row(s, journal.void(s, entry_id, body.reason))

    @app.get("/api/groupsets")
    def groupset_templates():
        return groupsets.list_templates()

    @app.post("/api/groupsets/{code}/plan")
    def groupset_plan(code: str, body: GroupsetPlanIn, s: Session = Depends(db)):
        return groupsets.plan(s, code, **body.model_dump())

    @app.post("/api/groupsets/{code}/import")
    def groupset_import(code: str, body: GroupsetImportIn, dry_run: bool = False, s: Session = Depends(db),
                        op_id: str | None = OpId):
        def fn():
            name = groupsets.get_template(code)["name"]
            ws = ws_svc.begin(s, at=body.at, bike_id=body.bike_id, title=f"Add groupset {name}", notes=body.notes)
            return groupsets.import_groupset(s, code, work_session_id=ws.id, **body.model_dump())
        return op(s, op_id, "groupset.import", fn, dry_run)

    # ------------------------------------------------------------ purchase bundles (e.g. a groupset)

    @app.get("/api/bundles")
    def bundles_list(bike_id: int | None = None, include_voided: bool = False, s: Session = Depends(db)):
        return bundles_svc.list_rows(s, bike_id=bike_id, include_voided=include_voided)

    @app.get("/api/bundles/candidates")
    def bundle_candidates(bike_id: int | None = None, s: Session = Depends(db)):
        return bundles_svc.candidates(s, bike_id=bike_id)

    @app.get("/api/bundles/{bundle_id}")
    def bundle_detail(bundle_id: int, s: Session = Depends(db)):
        return bundles_svc.row(s, bundles_svc.get(s, bundle_id))

    @app.post("/api/bundles", status_code=201)
    def bundle_create(body: BundleIn, s: Session = Depends(db), op_id: str | None = OpId):
        return op(s, op_id, "bundle.create",
                  lambda: bundles_svc.row(s, bundles_svc.create(s, **body.model_dump())))

    @app.patch("/api/bundles/{bundle_id}")
    def bundle_patch(bundle_id: int, body: BundlePatch, s: Session = Depends(db)):
        return bundles_svc.row(s, bundles_svc.update(s, bundle_id, **body.model_dump(exclude_unset=True)))

    @app.post("/api/bundles/{bundle_id}/members")
    def bundle_add(bundle_id: int, body: BundleMembersIn, s: Session = Depends(db)):
        return bundles_svc.row(s, bundles_svc.add_members(s, bundle_id, body.component_ids))

    @app.delete("/api/bundles/{bundle_id}/members/{component_id}")
    def bundle_remove(bundle_id: int, component_id: int, s: Session = Depends(db)):
        return bundles_svc.row(s, bundles_svc.remove_member(s, bundle_id, component_id))

    @app.post("/api/bundles/{bundle_id}/void")
    def bundle_void(bundle_id: int, body: VoidIn, s: Session = Depends(db)):
        return bundles_svc.row(s, bundles_svc.void(s, bundle_id, body.reason))

    @app.get("/api/work-sessions")
    def work_sessions(limit: int = 50, s: Session = Depends(db)):
        return ws_svc.recent(s, limit=limit)

    @app.get("/api/work-sessions/{ws_id}")
    def work_session(ws_id: int, s: Session = Depends(db)):
        return ws_svc.summary(s, ws_id)

    @app.post("/api/work-sessions/{ws_id}/undo")
    def undo_session(ws_id: int, body: UndoIn, dry_run: bool = False, s: Session = Depends(db),
                     op_id: str | None = OpId):
        return op(s, op_id, "worksession.undo", lambda: ws_svc.undo(s, ws_id, body.reason), dry_run)

    @app.post("/api/profiles", status_code=201)
    def add_profile(body: ProfileIn, s: Session = Depends(db)):
        if s.scalar(select(UsageProfile).where(UsageProfile.code == body.code)):
            raise DomainError(f"Profile {body.code} exists")
        p = UsageProfile(code=body.code, name=body.name, kind="TRAINER",
                         excluded_slots_json=json.dumps(body.excluded_slots),
                         excluded_types_json=json.dumps(body.excluded_types), notes=body.notes)
        s.add(p)
        s.flush()
        return {"id": p.id, "code": p.code}

    # ------------------------------------------------------------ imports, settings, data

    @app.post("/api/imports/csv")
    async def import_csv(request: Request, file_name: str | None = None):
        content = await request.body()
        if not content:
            raise DomainError("Empty upload")
        if len(content) > 20_000_000:
            raise DomainError("File too large (max 20 MB)")
        from starlette.concurrency import run_in_threadpool
        res = await run_in_threadpool(imports.run_csv_import, factory, content, file_name=file_name)
        log.info("CSV import %s: %s", file_name or "(upload)", res.get("counts"))
        return res

    @app.get("/api/product-templates")
    def product_templates():
        return product_import.templates()

    @app.get("/api/product-templates/instructions.md", response_class=PlainTextResponse)
    def product_template_instructions():
        return PlainTextResponse(product_import.agent_instructions(), media_type="text/markdown",
                                 headers={"Content-Disposition": 'attachment; filename="bikelog-import-instructions.md"'})

    @app.get("/api/product-templates/{component_type}/{kind}")
    def product_template(component_type: str, kind: str):
        if kind not in ("schema", "example"):
            raise DomainError("Ask for 'schema' or 'example'")
        doc = (product_import.schema if kind == "schema" else product_import.example)(component_type)
        name = f"{component_type.lower()}.{kind}.json"
        return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/imports/products")
    async def import_products(request: Request, dry_run: bool = False):
        content = await request.body()
        if not content:
            raise DomainError("Empty upload")
        if len(content) > 5_000_000:
            raise DomainError("File too large (max 5 MB)")
        from starlette.concurrency import run_in_threadpool
        res = await run_in_threadpool(product_import.run_import, factory, content, dry_run=dry_run)
        if not dry_run:
            log.info("JSON product import: %s; %d errors", res.get("counts"), len(res.get("errors") or []))
        return res

    @app.get("/api/imports")
    def import_batches(s: Session = Depends(db)):
        return imports.list_batches(s)

    @app.get("/api/imports/template", response_class=PlainTextResponse)
    def import_template():
        return PlainTextResponse(imports.CSV_TEMPLATE, media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="bikelog-rides-template.csv"'})

    @app.get("/api/strava/status")
    def strava_status(s: Session = Depends(db)):
        return strava_web.status(s)

    @app.put("/api/strava/credentials")
    def strava_credentials(body: StravaCredentialsIn):
        return strava_web.save_credentials(body.client_id, body.client_secret)

    @app.delete("/api/strava/credentials")
    def strava_forget_credentials():
        return strava_web.forget_credentials()

    @app.post("/api/strava/connect")
    def strava_connect(request: Request):
        port = request.url.port or 80
        return {"authorize_url": strava_web.start_connect(port), "redirect_uri": strava_web.redirect_uri(port)}

    @app.get("/api/strava/callback")
    def strava_callback(request: Request, state: str | None = None, code: str | None = None,
                        scope: str | None = None, error: str | None = None):
        import urllib.parse

        from fastapi.responses import RedirectResponse

        from bikelog.connectors.strava.client import StravaError
        back = f"http://127.0.0.1:{request.url.port or 80}/#/settings"
        try:
            res = strava_web.finish_connect(state=state, code=code, scope=scope, error=error)
            q = {"strava": "connected", "private": "1" if res["private_rides"] else "0"}
        except (DomainError, StravaError) as e:
            q = {"strava": "error", "message": str(e)[:300]}
        return RedirectResponse(back + "?" + urllib.parse.urlencode(q), status_code=303)

    @app.post("/api/strava/sync")
    def strava_sync_start(body: StravaSyncIn):
        return strava_web.start_sync(rescan=body.rescan)

    @app.post("/api/strava/disconnect")
    def strava_disconnect():
        return strava_web.disconnect()

    @app.get("/api/settings")
    def get_settings(s: Session = Depends(db)):
        return settings_svc.all_settings(s)

    @app.patch("/api/settings")
    def patch_settings(body: SettingsPatch, s: Session = Depends(db)):
        data = body.model_dump(exclude_unset=True)
        for k, v in data.items():
            settings_svc.set_value(s, k, v or "")
        if "timezone" in data:
            rebuild_everything(s)
        return settings_svc.all_settings(s)

    @app.post("/api/admin/rebuild")
    def rebuild(s: Session = Depends(db)):
        return {"rides": rebuild_everything(s)}

    @app.get("/api/changes")
    def changes(bike_id: int | None = None, component_id: int | None = None, limit: int = 500,
                s: Session = Depends(db)):
        if (bike_id is None) == (component_id is None):
            raise DomainError("Ask for the changes of one bike or one part")
        return changelog.entries(s, bike_id=bike_id, component_id=component_id, limit=min(limit, 2000))

    @app.get("/api/logs")
    def logs(lines: int = 300, level: str = "INFO"):
        return diagnostics.tail(paths, lines=lines, min_level=level.upper())

    @app.get("/api/logs/download", response_class=PlainTextResponse)
    def logs_download():
        return PlainTextResponse(diagnostics.full_text(paths), media_type="text/plain",
                                 headers={"Content-Disposition": 'attachment; filename="bikelog-log.txt"'})

    @app.get("/api/backups")
    def list_backups():
        files = sorted(paths.backups.glob("bikelog-*.db"), key=lambda p: p.name, reverse=True)
        return {"directory": str(paths.root), "backup_dir": str(paths.backups),
                "backups": [{"name": f.name, "size": f.stat().st_size, "kept": backup.KEPT_MARK in f.name} for f in files],
                "exports": [{"name": f.name, "size": f.stat().st_size}
                            for f in sorted(paths.exports.glob("*.zip"), reverse=True)]}

    @app.post("/api/backups", status_code=201)
    def create_backup():
        dest = backup.backup_database(paths, "manual")
        return {"name": dest.name if dest else None}

    @app.post("/api/admin/reset")
    def admin_reset(body: ResetIn):
        from bikelog import reset
        return reset.reset_database(factory, paths, confirm=body.confirm, clear_strava=body.clear_strava,
                                    strava_web=strava_web)

    @app.post("/api/backups/{name}/restore")
    def backup_restore(name: str):
        from bikelog import reset
        return reset.restore_backup(factory, paths, name, strava_web=strava_web)

    @app.post("/api/exports", status_code=201)
    def create_export():
        dest = backup.export_archive(paths, head_revision())
        return {"name": dest.name}

    @app.get("/api/exports/{name}")
    def download_export(name: str):
        f = (paths.exports / name).resolve()
        if f.parent != paths.exports.resolve() or not f.exists():
            raise DomainError("No such export")
        return FileResponse(f, filename=name, media_type="application/zip")

    # ------------------------------------------------------------ frontend

    if static and (static / "index.html").exists():
        index_html = (static / "index.html").read_text(encoding="utf-8").replace("%BIKELOG_TOKEN%", token)

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def index():
            return HTMLResponse(index_html, headers={"Cache-Control": "no-store"})

        app.mount("/", StaticFiles(directory=static), name="static")
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def no_frontend():
            return HTMLResponse("<h1>Bike Log</h1><p>The frontend is not built. Run <code>npm run build</code> in "
                                "frontend/ (see HANDOVER.md). The API is available under /api.</p>")
    return app


def _find_static() -> Path | None:
    for cand in (resource_root() / "static", Path(__file__).resolve().parents[3] / "frontend" / "dist"):
        if (cand / "index.html").exists():
            return cand
    return None


# ---------------------------------------------------------------- serializers

def _bike_summary(s: Session, b: Bike, attribution: dict | None = None) -> dict:
    usage = bike_usage(s, b)
    cost = costs_svc.bike_costs(s, b, attribution=attribution, with_items=False)
    cost["per_km_cents"] = costs_svc.per_km(cost, usage["total_km"])
    return {"id": b.id, "uuid": b.uuid, "name": b.name, "maker": b.maker, "model": b.model, "year": b.year,
            "status": b.status, "strava_gear_id": b.strava_gear_id, "notes": b.notes, "usage": usage,
            "purchase_price_cents": b.purchase_price_cents, "purchase_date": b.purchase_date, "costs": cost,
            "shifting": b.shifting, "shifting_effective": inv.shifting_of(s, b),
            "open_tasks": sum(1 for t in m.queue(s, bike_id=b.id) if t["status"] in ("DUE", "OVERDUE", "ATTENTION"))}


def _product(p: Product) -> dict:
    return {"compatibility": spares.compatibility(object_session(p), p.id),"id": p.id, "uuid": p.uuid, "component_type": p.component_type, "maker": p.maker, "model": p.model,
            "specs": json.loads(p.specs_json or "{}"), "spec_source": p.spec_source, "spec_version": p.spec_version,
            "notes": p.notes, "list_price_cents": p.list_price_cents}


def _bundle_ref(s: Session, c: Component) -> dict | None:
    if not c.bundle_id:
        return None
    b = bundles_svc.get(s, c.bundle_id)
    if b.voided_at:
        return None
    return {"id": b.id, "name": b.name, "merchant": b.merchant, "purchased_on": b.purchased_on,
            "price_cents": b.price_cents, "share_cents": bundles_svc.shares(s, b).get(c.id)}


def _component_summary(s: Session, c: Component) -> dict:
    t = COMPONENT_TYPES.get(c.component_type)
    setup, wheel = inv.tire_setup_of(s, c)
    return {"id": c.id, "uuid": c.uuid, "label": c.label, "component_type": c.component_type,
            "type_name": t.name if t else c.component_type, "category": t.category if t else None,
            "product_id": c.product_id,
            "product": f"{c.product.maker or ''} {c.product.model}".strip() if c.product else None,
            "prior_usage": c.prior_usage, "status": c.status, "purchase_date": c.purchase_date,
            "price_cents": c.price_cents, "serial_number": c.serial_number, "notes": c.notes,
            "retired_on": c.retired_on, "retire_reason": c.retire_reason, "disposition": c.disposition,
            "storage_location": c.storage_location, "tire_setup": c.tire_setup, "bundle": _bundle_ref(s, c),
            "effective_tire_setup": setup, "tire_setup_from": wheel.label if wheel is not None and wheel.id != c.id else None,
            "location": inv.location(s, c), "usage": component_usage(s, c)}
