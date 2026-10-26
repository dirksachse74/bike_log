"""Reference data that ships with the code: component types, slots, maintenance actions,
default service rules and usage profiles.

Types and actions are versioned with the application (they drive behaviour). Default rules and
usage profiles are copied into the database on first start so the user can change intervals.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentType:
    code: str
    name: str
    category: str
    slots: tuple[str, ...] = ()          # allowed slots; first is the default
    parent_types: tuple[str, ...] = ()   # may be mounted on these component types instead of a bike
    tracks_distance: bool = True         # False: calendar-only parts (e.g. brake fluid circuit)
    removed_default: str = "STORED"      # suggested answer to "What happened to the old item?"
    rider_gear: bool = False             # worn by the rider (shoes): counts every ride while "in use"
    torque: bool = False                 # bolted on with a torque spec: part of the bike's torque check


@dataclass(frozen=True)
class Action:
    code: str
    name: str
    kind: str                       # LUBRICATE, INSPECT, MEASURE, SERVICE, CLEAN, REPAIR, CHARGE, NOTE
    targets: tuple[str, ...]        # component type codes, "BIKE" for the whole bike, or ("*",) for all
    quick: bool = False             # offered as one-tap shortcut
    fields: tuple[str, ...] = ()    # extra inputs: symptom, work_done, outcome, measurement, consumable
    outcomes: tuple[str, ...] = ()  # allowed outcome codes (empty = free text)
    attention_outcomes: tuple[str, ...] = ()  # outcomes that need attention until a later event
    limits: tuple["Limit", ...] = ()          # a measurement sets the outcome (worst limit reached first)
    unit: str | None = None                   # unit the limits are in (also the default unit)
    limits_source: str | None = None
    checklist: tuple[str, ...] = ()           # jobs to tick off when logging it (e.g. the yearly full service)


@dataclass(frozen=True)
class Limit:
    """``outcome`` once the measurement is at or past ``value``: below it for wear left (pads, rotors),
    above it for stretch (chain)."""
    value: float
    outcome: str
    below: bool = True


POWER_METERS = ("POWER_METER", "POWER_METER_PEDALS")
# The big jobs of the yearly full service. Logging the full service records which ones were ticked; each job
# still has its own reminder on its part (bleed, bearings ...), which the full service does not reset.
FULL_SERVICE_CHECKLIST = (
    "Wheel hub bearings: play and roughness",
    "Headset: clean, grease, check play",
    "Bottom bracket: play and noise",
    "Brakes: bleed (or check lever feel), hoses, pads, rotors",
    "Di2 wires and junction / shift cables and housing",
    "Frame and fork: cracks, dents, chips",
    "Drivetrain: deep clean, chain, cassette and chainring wear",
    "Pedals: bearing play",
    "Torque check of all bolts",
)
# actions that charge a battery: a charge reminder needs one logged charge before it can count
CHARGE_ACTIONS = ("BATTERY_CHARGE", "POWER_CHARGE")

COMPONENT_TYPES: dict[str, ComponentType] = {t.code: t for t in [
    ComponentType("CHAIN", "Chain", "Drivetrain", ("CHAIN",)),
    ComponentType("DERAILLEUR_HANGER", "Derailleur hanger", "Frame", ("HANGER",), torque=True),
    ComponentType("QUICK_LINK", "Quick link", "Drivetrain", ("QUICK_LINK",), ("CHAIN",), removed_default="DISCARDED"),
    ComponentType("CASSETTE", "Cassette", "Drivetrain", ("CASSETTE",), ("REAR_WHEEL",), torque=True),
    ComponentType("CRANKSET", "Crankset", "Drivetrain", ("CRANKSET",), torque=True),
    ComponentType("CHAINRING", "Chainring", "Drivetrain", ("CHAINRING_OUTER", "CHAINRING_INNER"), ("CRANKSET",)),
    ComponentType("BOTTOM_BRACKET", "Bottom bracket", "Drivetrain", ("BOTTOM_BRACKET",), torque=True),
    ComponentType("REAR_DERAILLEUR", "Rear derailleur", "Drivetrain", ("REAR_DERAILLEUR",), torque=True),
    ComponentType("PULLEY_WHEEL", "Pulley wheel", "Drivetrain", ("PULLEY_UPPER", "PULLEY_LOWER"),
                  ("REAR_DERAILLEUR",), removed_default="DISCARDED"),
    ComponentType("FRONT_DERAILLEUR", "Front derailleur", "Drivetrain", ("FRONT_DERAILLEUR",), torque=True),
    # mechanical shifting only: their rules run when the bike's shifting is mechanical
    ComponentType("SHIFT_CABLE", "Shift cable", "Drivetrain", ("SHIFT_CABLE_REAR", "SHIFT_CABLE_FRONT"),
                  removed_default="DISCARDED"),
    ComponentType("SHIFT_HOUSING", "Shift housing", "Drivetrain", ("SHIFT_HOUSING_REAR", "SHIFT_HOUSING_FRONT"),
                  removed_default="DISCARDED"),
    # A wheelset holds the two wheels; the wheels hold tires, tubes, rotors, cassette, hub, spokes, rim tape.
    # Every part keeps its own km; moving the wheelset moves everything on it.
    ComponentType("WHEELSET", "Wheelset", "Wheels", ("WHEELSET",)),
    ComponentType("FRONT_WHEEL", "Front wheel", "Wheels", ("FRONT_WHEEL",), ("WHEELSET",), torque=True),
    ComponentType("REAR_WHEEL", "Rear wheel", "Wheels", ("REAR_WHEEL",), ("WHEELSET",), torque=True),
    ComponentType("HUB", "Hub", "Wheels", ("HUB",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("HUB_BEARINGS", "Hub bearings (set)", "Wheels", ("BEARINGS",), ("HUB",), removed_default="DISCARDED"),
    ComponentType("SPOKES", "Spokes (set)", "Wheels", ("SPOKES",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("RIM_TAPE", "Rim tape", "Wheels", ("RIM_TAPE",), ("FRONT_WHEEL", "REAR_WHEEL"),
                  removed_default="DISCARDED"),
    ComponentType("TUBELESS_VALVE", "Tubeless valve", "Wheels", ("VALVE",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("TIRE", "Tire", "Wheels", ("TIRE",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("INNER_TUBE", "Inner tube", "Wheels", ("TUBE",), ("FRONT_WHEEL", "REAR_WHEEL"),
                  removed_default="AWAITING_SERVICE"),
    ComponentType("BRAKE_ROTOR", "Brake rotor", "Brakes", ("ROTOR",), ("FRONT_WHEEL", "REAR_WHEEL"), torque=True),
    ComponentType("BRAKE_CIRCUIT", "Brake circuit (hydraulic)", "Brakes", ("FRONT_BRAKE", "REAR_BRAKE"),
                  tracks_distance=True, torque=True),
    ComponentType("BRAKE_PADS", "Brake pads", "Brakes", ("FRONT_PADS", "REAR_PADS"), removed_default="DISCARDED"),
    ComponentType("POWER_METER", "Power meter", "Drivetrain", ("POWER_METER",), ("CRANKSET",)),
    ComponentType("HEADSET", "Headset", "Frame", ("HEADSET",), torque=True),
    ComponentType("PEDALS", "Pedals", "Contact points", ("PEDALS",), torque=True),
    ComponentType("POWER_METER_PEDALS", "Power-meter pedals", "Contact points", ("PEDALS",), torque=True),
    # shoes are worn, not mounted: while in use they count every ride on any bike; cleats sit on the shoes
    ComponentType("SHOES", "Cycling shoes", "Contact points", ("RIDER",), rider_gear=True),
    ComponentType("CLEATS", "Cleats", "Contact points", ("CLEATS",), ("SHOES",), removed_default="DISCARDED"),
    ComponentType("SADDLE", "Saddle", "Contact points", ("SADDLE",), torque=True),
    ComponentType("SEATPOST", "Seatpost", "Contact points", ("SEATPOST",), torque=True),
    ComponentType("STEM", "Stem", "Cockpit", ("STEM",), torque=True),
    ComponentType("HANDLEBAR", "Handlebar", "Cockpit", ("HANDLEBAR",), torque=True),
    ComponentType("BAR_TAPE", "Bar tape", "Cockpit", ("BAR_TAPE",), removed_default="DISCARDED"),
    ComponentType("SHIFTERS", "Shifters", "Controls", ("SHIFTERS",), torque=True),
    # Di2: one battery on the bike; SRAM AXS: one battery on each derailleur
    ComponentType("BATTERY", "Battery (Di2/AXS)", "Electronics", ("BATTERY",), ("FRONT_DERAILLEUR", "REAR_DERAILLEUR")),
    # speed/cadence sensor: on a wheel (moves with the wheelset), on the crankset or on the bike
    ComponentType("SENSOR", "Sensor (speed/cadence)", "Electronics", ("SENSOR_SPEED", "SENSOR_CADENCE"),
                  ("FRONT_WHEEL", "REAR_WHEEL", "CRANKSET")),
    ComponentType("BIKE_COMPUTER", "Bike computer", "Electronics", ("COMPUTER",)),
    ComponentType("LIGHT", "Light", "Electronics", ("LIGHT_FRONT", "LIGHT_REAR")),
    ComponentType("RADAR", "Radar", "Electronics", ("RADAR",)),
    ComponentType("OTHER", "Other part", "Other", ()),
]}

ALL = ("*",)
BIKE = "BIKE"          # target of bike-level actions and rules (torque check, frame inspection)
RIDER_GEAR_TYPES = tuple(t.code for t in COMPONENT_TYPES.values() if t.rider_gear)
TORQUE_TYPES = tuple(t.code for t in COMPONENT_TYPES.values() if t.torque)

# What happened to an item that is no longer installed. RETIRED, DISCARDED and SOLD take it out of
# use (component.status = RETIRED); its record, mileage and history are always kept.
DISPOSITIONS: dict[str, str] = {
    "STORED": "Stored as a reusable spare",
    "AWAITING_SERVICE": "Awaiting inspection or repair",
    "RETIRED": "Retired from use",
    "DISCARDED": "Discarded",
    "SOLD": "Sold or given away",
    "IN_USE": "In use (worn by the rider)",     # rider gear (shoes) only
}
OUT_OF_USE = ("RETIRED", "DISCARDED", "SOLD")

# Stock units for spare parts held as a quantity. One unit is one usable item, never "one package":
# a pack of two quick links is two units (record packages separately on the purchase).
STOCK_UNITS: dict[str, tuple[str, str]] = {
    "INNER_TUBE": ("tube", "one tube"),
    "BRAKE_PADS": ("set", "one pad set for one caliper"),
    "BRAKE_ROTOR": ("rotor", "one rotor"),
    "CHAIN": ("chain", "one complete chain"),
    "QUICK_LINK": ("link", "one complete connector"),
    "BAR_TAPE": ("package", "one package; record its coverage (e.g. one handlebar)"),
    "TIRE": ("tire", "one tire"),
}

# Consumable tracking modes (individual items are components, see COMPONENT_TYPES).
TRACKING_MODES: dict[str, str] = {
    "COUNTED": "Counted stock (patches, quick links, coin cells): whole pieces",
    "BULK": "Bulk supply (wax, sealant, fluid, grease): container quantity, amount used optional",
}

ACTIONS: dict[str, Action] = {a.code: a for a in [
    # chain
    Action("WAX_HOT", "Hot wax", "LUBRICATE", ("CHAIN",), quick=True, fields=("consumable",)),
    Action("WAX_LIQUID", "Liquid wax top-up", "LUBRICATE", ("CHAIN",), quick=True, fields=("consumable",)),
    Action("LUBE", "Lube chain (oil / drip)", "LUBRICATE", ("CHAIN",), quick=True, fields=("consumable",)),
    Action("CHAIN_STRIP", "Strip / clean chain", "CLEAN", ("CHAIN",)),
    Action("CHAIN_MEASURE_WEAR", "Measure chain wear", "MEASURE", ("CHAIN",), quick=True,
           fields=("measurement", "outcome"), outcomes=("OK", "APPROACHING_LIMIT", "AT_LIMIT"),
           attention_outcomes=("APPROACHING_LIMIT", "AT_LIMIT"), unit="%",
           limits=(Limit(0.5, "AT_LIMIT", below=False), Limit(0.4, "APPROACHING_LIMIT", below=False)),
           limits_source="12-speed: replace at 0.5 % (shop guidance, e.g. Shimano TL-CN42 drops in); "
                         "0.4 % warning is a personal margin"),
    # brakes
    Action("BRAKE_FLUID_REPLACE", "Full brake-fluid replacement", "SERVICE", ("BRAKE_CIRCUIT",),
           fields=("consumable", "work_done", "outcome")),
    Action("BRAKE_BLEED", "Bleed brake", "SERVICE", ("BRAKE_CIRCUIT",),
           fields=("symptom", "work_done", "outcome", "consumable"),
           outcomes=("RESOLVED", "IMPROVED", "NOT_RESOLVED"), attention_outcomes=("NOT_RESOLVED",)),
    Action("BRAKE_CHECK", "Check brake (lever feel, leaks)", "INSPECT", ("BRAKE_CIRCUIT",), quick=True,
           fields=("symptom", "outcome"), outcomes=("OK", "SPONGY", "LEAK", "NOISE"),
           attention_outcomes=("SPONGY", "LEAK")),
    Action("PAD_MEASURE", "Measure pad material", "MEASURE", ("BRAKE_PADS",), quick=True,
           fields=("measurement", "outcome"), outcomes=("OK", "LOW", "AT_LIMIT"),
           attention_outcomes=("LOW", "AT_LIMIT"), unit="mm", limits=(Limit(0.5, "AT_LIMIT"), Limit(1.0, "LOW")),
           limits_source="Shimano: replace before the pad material is under 0.5 mm; 1.0 mm is the practical "
                         "warning point (Shimano tune-up guide)"),
    Action("ROTOR_MEASURE", "Measure rotor thickness", "MEASURE", ("BRAKE_ROTOR",),
           fields=("measurement", "outcome"), outcomes=("OK", "LOW", "AT_LIMIT"), attention_outcomes=("LOW", "AT_LIMIT"),
           unit="mm", limits=(Limit(1.5, "AT_LIMIT"), Limit(1.6, "LOW")),
           limits_source="Shimano rotors: 1.8 mm new, replace at 1.5 mm (printed on the rotor); check yours"),
    Action("BED_IN", "Bed in pads and rotors", "SERVICE", ("BRAKE_PADS", "BRAKE_ROTOR")),
    Action("HOSE_INSPECT", "Inspect brake hoses and caliper (leaks, kinks)", "INSPECT", ("BRAKE_CIRCUIT",),
           fields=("outcome",), outcomes=("OK", "LEAK", "DAMAGE"), attention_outcomes=("LEAK", "DAMAGE")),
    Action("PISTON_CLEAN", "Clean and reset caliper pistons", "CLEAN", ("BRAKE_CIRCUIT",)),
    # wheels: inspection, hub bearings and freehub are deliberately separate actions
    Action("WHEEL_INSPECT", "Inspect wheel (trueness, spokes, rim)", "INSPECT", ("FRONT_WHEEL", "REAR_WHEEL"),
           quick=True, fields=("outcome",), outcomes=("OK", "OUT_OF_TRUE", "DAMAGE"),
           attention_outcomes=("OUT_OF_TRUE", "DAMAGE")),
    Action("WHEEL_TRUE", "True wheel", "SERVICE", ("FRONT_WHEEL", "REAR_WHEEL")),
    Action("HUB_BEARING_SERVICE", "Service hub bearings", "SERVICE", ("FRONT_WHEEL", "REAR_WHEEL"),
           fields=("work_done", "consumable")),
    Action("FREEHUB_SERVICE", "Service freehub", "SERVICE", ("REAR_WHEEL",), fields=("work_done", "consumable")),
    Action("THRU_AXLE_SERVICE", "Check and grease thru-axle", "SERVICE", ("FRONT_WHEEL", "REAR_WHEEL"),
           fields=("consumable",)),
    Action("VALVE_CORE_REPLACE", "Replace valve core", "SERVICE", ("TUBELESS_VALVE",)),
    # tires
    Action("SEALANT_TOP_UP", "Top up sealant", "SERVICE", ("TIRE",), quick=True, fields=("consumable",)),
    Action("SEALANT_RENEW", "Renew sealant", "SERVICE", ("TIRE",), fields=("consumable",)),
    Action("TIRE_INSPECT", "Inspect tire (tread, cuts, sidewall cracks)", "INSPECT", ("TIRE",), quick=True,
           fields=("outcome",), outcomes=("OK", "CUT", "WORN", "CRACKED"), attention_outcomes=("CUT", "WORN", "CRACKED")),
    Action("TUBE_PATCH", "Patch tube", "REPAIR", ("INNER_TUBE",), fields=("symptom", "outcome", "consumable"),
           outcomes=("REPAIRED", "NOT_REPAIRABLE")),
    # headset and power meter
    Action("HEADSET_SERVICE", "Service headset (clean, grease, check play)", "SERVICE", ("HEADSET",),
           fields=("symptom", "work_done", "outcome", "consumable")),
    Action("POWER_ZERO_OFFSET", "Zero offset / calibrate power meter", "SERVICE", POWER_METERS, quick=True),
    Action("POWER_CHARGE", "Charged", "CHARGE", POWER_METERS, quick=True),
    Action("POWER_BATTERY", "Replace power-meter battery (coin cell)", "SERVICE", POWER_METERS,
           fields=("consumable",)),
    Action("POWER_FIRMWARE", "Update power-meter firmware", "SERVICE", POWER_METERS, fields=("work_done",)),
    # electronic shifting: the shifters' coin cells (wireless Di2 levers)
    Action("COIN_CELL_REPLACE", "Replace coin-cell battery", "SERVICE", ("SHIFTERS", "SENSOR"), quick=True,
           fields=("consumable",)),
    # drivetrain wear checks for parts inside parts
    Action("PULLEY_INSPECT", "Check pulley wheels (play, worn teeth, noise)", "INSPECT", ("PULLEY_WHEEL",),
           quick=True, fields=("outcome",), outcomes=("OK", "WORN", "NOISY"), attention_outcomes=("WORN", "NOISY")),
    Action("CHAINRING_INSPECT", "Check chainring wear (teeth shape, chain suck)", "INSPECT", ("CHAINRING",),
           quick=True, fields=("outcome",), outcomes=("OK", "WORN"), attention_outcomes=("WORN",)),
    Action("QUICK_LINK_CHECK", "Check quick link (closes with a firm snap, not loose)", "INSPECT", ("QUICK_LINK",),
           quick=True, fields=("outcome",), outcomes=("OK", "LOOSE"), attention_outcomes=("LOOSE",)),
    Action("RIM_TAPE_CHECK", "Check rim tape (tubeless: leaks at spoke holes)", "INSPECT", ("RIM_TAPE",),
           fields=("outcome",), outcomes=("OK", "LEAKING", "DAMAGED"), attention_outcomes=("LEAKING", "DAMAGED")),
    Action("CASSETTE_INSPECT", "Check cassette wear (teeth, skipping with the new chain)", "INSPECT", ("CASSETTE",),
           quick=True, fields=("outcome",), outcomes=("OK", "WORN"), attention_outcomes=("WORN",)),
    Action("PEDAL_SERVICE", "Service pedal bearings (play, regrease)", "SERVICE", ("PEDALS", "POWER_METER_PEDALS"),
           fields=("work_done", "consumable")),
    Action("BB_INSPECT", "Check bottom bracket (play, creaks, rough bearings)", "INSPECT", ("BOTTOM_BRACKET",),
           fields=("outcome",), outcomes=("OK", "PLAY", "CREAK", "ROUGH"), attention_outcomes=("PLAY", "CREAK", "ROUGH")),
    Action("HANGER_ALIGN", "Check derailleur hanger alignment", "INSPECT", ("DERAILLEUR_HANGER",), quick=True,
           fields=("outcome",), outcomes=("OK", "STRAIGHTENED", "BENT"), attention_outcomes=("BENT",)),
    Action("CLEAT_INSPECT", "Inspect cleats (wear pads, float, clipping)", "INSPECT", ("CLEATS",), quick=True,
           fields=("outcome",), outcomes=("OK", "WORN"), attention_outcomes=("WORN",)),
    Action("CABLE_INSPECT", "Check shift cable and housing (fraying, friction)", "INSPECT",
           ("SHIFT_CABLE", "SHIFT_HOUSING"), fields=("outcome",), outcomes=("OK", "FRAYED", "FRICTION"),
           attention_outcomes=("FRAYED", "FRICTION")),
    Action("SEATPOST_SERVICE", "Remove, clean and re-paste seatpost", "SERVICE", ("SEATPOST",),
           fields=("consumable",)),
    # cockpit
    Action("BAR_TAPE_REWRAP", "Rewrap bar tape (same tape)", "SERVICE", ("BAR_TAPE",), fields=("work_done",)),
    Action("BAR_TAPE_INSPECT", "Inspect bar tape (worn, torn, slippery)", "INSPECT", ("BAR_TAPE",), quick=True,
           fields=("outcome",), outcomes=("OK", "WORN"), attention_outcomes=("WORN",)),
    # the whole bike
    Action("TORQUE_CHECK", "Torque check (stem, bars, seatpost, cranks, rotors, thru-axles)", "INSPECT", (BIKE,),
           quick=True, fields=("work_done",)),
    Action("FRAME_INSPECT", "Frame and fork inspection (cracks, dents, chips)", "INSPECT", (BIKE,),
           fields=("outcome", "symptom"), outcomes=("OK", "DAMAGE"), attention_outcomes=("DAMAGE",)),
    Action("DI2_SYSTEM_CHECK", "Di2 check in E-TUBE (firmware, error log)", "SERVICE", (BIKE,),
           fields=("work_done", "outcome"), outcomes=("OK", "UPDATED", "ERROR"), attention_outcomes=("ERROR",)),
    Action("DI2_WIRE_INSPECT", "Inspect Di2 wires and junction", "INSPECT", (BIKE,),
           fields=("outcome",), outcomes=("OK", "DAMAGE"), attention_outcomes=("DAMAGE",)),
    Action("SHIFT_ADJUST", "Adjust shifting", "SERVICE", (BIKE,), fields=("symptom", "work_done")),
    Action("FULL_SERVICE", "Full service (whole bike)", "SERVICE", (BIKE,), fields=("work_done",),
           checklist=FULL_SERVICE_CHECKLIST),
    # generic
    Action("INSPECT", "Record inspection", "INSPECT", ALL, quick=True, fields=("outcome",),
           outcomes=("OK", "MONITOR", "WORN", "DAMAGE"), attention_outcomes=("MONITOR", "WORN", "DAMAGE")),
    Action("CLEAN", "Clean", "CLEAN", ALL),
    Action("SERVICE", "General service", "SERVICE", ALL, fields=("work_done",)),
    Action("REPAIR", "Repair", "REPAIR", ALL, fields=("symptom", "work_done", "outcome", "consumable")),
    Action("BATTERY_CHARGE", "Charged", "CHARGE", ("BATTERY", "BIKE_COMPUTER", "LIGHT", "RADAR"), quick=True),
]}


def action_applies(action: Action, component_type: str) -> bool:
    """Generic actions (clean, inspect, service, repair) also apply to the whole bike."""
    return action.targets == ALL or component_type in action.targets


def outcome_from_measurement(action: Action, value: float | None, unit: str | None) -> str | None:
    """The outcome a measurement implies, or None when the action has no limits or the unit differs."""
    if not action.limits or value is None or (unit and action.unit and unit.strip().lower() != action.unit.lower()):
        return None
    for lim in action.limits:   # listed worst first
        if (value <= lim.value) if lim.below else (value >= lim.value):
            return lim.outcome
    return "OK"


@dataclass(frozen=True)
class DefaultRule:
    rule_code: str
    name: str
    component_type: str
    action_code: str
    trigger: str = "INTERVAL"                # INTERVAL | CYCLE_WINDOW | PARENT_COUNT | ONCE_AFTER_INSTALL
    interval_km: float | None = None
    interval_months: int | None = None
    window_min_km: float | None = None
    window_max_km: float | None = None
    cycle_action_code: str | None = None     # CYCLE_WINDOW: action that starts a new cycle
    reset_actions: tuple[str, ...] = ()      # default: (action_code,)
    warn_km: float | None = None
    warn_days: int | None = None
    warn_hours: float | None = None
    origin: str = "DEFAULT"
    requires_setup: str | None = None        # tire setup of the part's wheel, or shifting of its bike
    interval_hours: float | None = None      # INTERVAL: ride time since the last reset action
    interval_count: int | None = None        # PARENT_COUNT: due once the part has been on this many parents
    active: bool = True                      # False: offered but switched off until you turn it on
    notes: str | None = None                 # where the number comes from


DEFAULT_RULES: list[DefaultRule] = [
    DefaultRule("CHAIN_HOT_WAX", "Hot wax chain", "CHAIN", "WAX_HOT", interval_km=500, warn_km=50),
    DefaultRule("CHAIN_LIQUID_WAX", "Liquid-wax top-up", "CHAIN", "WAX_LIQUID", trigger="CYCLE_WINDOW",
                window_min_km=250, window_max_km=300, cycle_action_code="WAX_HOT", warn_km=25),
    DefaultRule("CHAIN_WEAR_CHECK", "Measure chain wear", "CHAIN", "CHAIN_MEASURE_WEAR", interval_km=1000,
                warn_km=100),
    DefaultRule("BRAKE_FLUID", "Replace brake fluid", "BRAKE_CIRCUIT", "BRAKE_FLUID_REPLACE",
                interval_months=24, warn_days=30),
    DefaultRule("BRAKE_PAD_CHECK", "Check brake pads", "BRAKE_PADS", "PAD_MEASURE", interval_km=1000, warn_km=100),
    DefaultRule("FRONT_WHEEL_INSPECTION", "Inspect wheel", "FRONT_WHEEL", "WHEEL_INSPECT",
                interval_km=3000, interval_months=12, warn_km=200, warn_days=30),
    DefaultRule("REAR_WHEEL_INSPECTION", "Inspect wheel", "REAR_WHEEL", "WHEEL_INSPECT",
                interval_km=3000, interval_months=12, warn_km=200, warn_days=30),
    DefaultRule("FRONT_HUB_BEARINGS", "Service hub bearings", "FRONT_WHEEL", "HUB_BEARING_SERVICE",
                interval_km=10000, warn_km=500),
    DefaultRule("REAR_HUB_BEARINGS", "Service hub bearings", "REAR_WHEEL", "HUB_BEARING_SERVICE",
                interval_km=10000, warn_km=500),
    DefaultRule("FREEHUB", "Service freehub", "REAR_WHEEL", "FREEHUB_SERVICE",
                interval_km=5000, interval_months=12, warn_km=300, warn_days=30),
    DefaultRule("TIRE_CHECK", "Inspect tire", "TIRE", "TIRE_INSPECT", interval_km=1000, warn_km=100,
                interval_months=12, warn_days=30,
                notes="Yearly also for sidewall cracks from age; no bicycle-tire age limit was found."),
    # sealant dries out with time, not distance; renewing it also resets the top-up reminder
    DefaultRule("TIRE_SEALANT", "Top up sealant", "TIRE", "SEALANT_TOP_UP", interval_months=3, warn_days=14,
                reset_actions=("SEALANT_TOP_UP", "SEALANT_RENEW"), requires_setup="TUBELESS", origin="MANUFACTURER",
                notes="Stan's: sealant lasts 2–6 months; check every 3 months (stans.com sealant support)."),
    DefaultRule("TIRE_SEALANT_RENEW", "Clean out and renew sealant", "TIRE", "SEALANT_RENEW", interval_months=12,
                warn_days=30, requires_setup="TUBELESS", origin="MANUFACTURER",
                notes="Stan's: take the tire off and clean out old sealant once a year; check rim tape and "
                      "valves at the same time (stans.com sealant support)."),
    DefaultRule("VALVE_CORE", "Replace valve core", "TUBELESS_VALVE", "VALVE_CORE_REPLACE", interval_months=12,
                warn_days=30, requires_setup="TUBELESS", notes="At the yearly sealant clean-out; personal value."),
    DefaultRule("FRONT_THRU_AXLE", "Check and grease thru-axle", "FRONT_WHEEL", "THRU_AXLE_SERVICE",
                interval_months=6, warn_days=14, notes="Personal value."),
    DefaultRule("REAR_THRU_AXLE", "Check and grease thru-axle", "REAR_WHEEL", "THRU_AXLE_SERVICE",
                interval_months=6, warn_days=14, notes="Personal value."),
    DefaultRule("HEADSET_SERVICE", "Service headset", "HEADSET", "HEADSET_SERVICE",
                interval_km=5000, interval_months=12, warn_km=300, warn_days=30),
    # batteries (figures from retailer listings quoting the makers; not verified with the makers)
    DefaultRule("DI2_BATTERY_CHARGE", "Charge Di2 battery", "BATTERY", "BATTERY_CHARGE", interval_km=800, warn_km=100,
                notes="Shimano BT-DN300: about 1000 km per charge (less with much front shifting); 800 km leaves a "
                      "margin. Source: retailer listings (Rose, Tweeks), not verified with Shimano."),
    DefaultRule("POWER_METER_CHARGE", "Charge power meter", "POWER_METER", "POWER_CHARGE", interval_hours=50,
                warn_hours=10, notes="Set to your power meter's battery life with a margin."),
    DefaultRule("POWER_PEDALS_CHARGE", "Charge power-meter pedals", "POWER_METER_PEDALS", "POWER_CHARGE",
                interval_hours=80, warn_hours=10,
                notes="Favero Assioma PRO RS-1: at least 60 h per charge (up to about 160 h after a firmware "
                      "update). 80 h is your choice (2026-10-26). Source: retailer listings quoting Favero, "
                      "not verified."),
    DefaultRule("SENSOR_BATTERY", "Replace sensor battery", "SENSOR", "COIN_CELL_REPLACE", interval_hours=400,
                warn_hours=40, interval_months=12, warn_days=30,
                notes="Magene S3+ (CR2032): about 500 h of riding per battery (retailer listings, not verified with "
                      "Magene); 400 h leaves a margin. 12 months covers standby drain (your estimate)."),
    DefaultRule("SHIFTER_COIN_CELLS", "Replace shifter coin cells", "SHIFTERS", "COIN_CELL_REPLACE",
                interval_months=18, warn_days=30, active=False,
                notes="Wireless Di2 levers (CR1632): about 1.5–2 years (retailer listings); 18 months leaves a "
                      "margin. Off by default (wired and mechanical levers have no coin cell); switch it on for "
                      "wireless levers. Keep CR1632 cells as counted stock to pick them when logging."),
    DefaultRule("COMPUTER_CHARGE", "Charge bike computer", "BIKE_COMPUTER", "BATTERY_CHARGE", interval_hours=20,
                warn_hours=4, notes="Set to your device's battery life with a margin (personal value)."),
    DefaultRule("LIGHT_CHARGE", "Charge light", "LIGHT", "BATTERY_CHARGE", interval_hours=4, warn_hours=1,
                notes="Set to your light's run time in the mode you use (personal value)."),
    DefaultRule("RADAR_CHARGE", "Charge radar", "RADAR", "BATTERY_CHARGE", interval_hours=6, warn_hours=2,
                notes="Set to your radar's run time in the mode you use (personal value)."),
    # parts inside parts
    DefaultRule("PULLEY_CHECK", "Check pulley wheels", "PULLEY_WHEEL", "PULLEY_INSPECT", interval_km=5000,
                warn_km=300, notes="Common workshop practice, not a maker's figure."),
    DefaultRule("CHAINRING_CHECK", "Check chainring wear", "CHAINRING", "CHAINRING_INSPECT", interval_km=5000,
                warn_km=300, notes="Check at least at every chain change; common practice, not a maker's figure."),
    DefaultRule("QUICK_LINK_CHAINS", "Replace quick link", "QUICK_LINK", "QUICK_LINK_CHECK", trigger="PARENT_COUNT",
                interval_count=2,
                notes="Wippermann Connex links are sold as reusable many times; no official limit was found. "
                      "Replace after 2 chains (your choice) or as soon as it closes noticeably looser than new."),
    DefaultRule("RIM_TAPE_CHECK", "Check rim tape", "RIM_TAPE", "RIM_TAPE_CHECK", interval_months=12, warn_days=30,
                notes="Check at every tire change or yearly (tubes: tape covers the spoke holes; tubeless: it seals)."),
    # brakes
    DefaultRule("HOSE_CHECK", "Inspect brake hoses and caliper", "BRAKE_CIRCUIT", "HOSE_INSPECT", interval_months=12,
                warn_days=30, reset_actions=("HOSE_INSPECT", "BRAKE_FLUID_REPLACE"),
                notes="With every fluid change or yearly; personal value."),
    DefaultRule("PAD_BED_IN", "Bed in new pads", "BRAKE_PADS", "BED_IN", trigger="ONCE_AFTER_INSTALL",
                window_max_km=100, notes="Once after fitting; after 100 km without it the pads count as bedded in."),
    DefaultRule("ROTOR_BED_IN", "Bed in new rotor", "BRAKE_ROTOR", "BED_IN", trigger="ONCE_AFTER_INSTALL",
                window_max_km=100, notes="Once after fitting; after 100 km without it the rotor counts as bedded in."),
    # contact points and frame
    DefaultRule("PEDAL_BEARINGS", "Service pedal bearings", "PEDALS", "PEDAL_SERVICE", interval_km=5000,
                interval_months=12, warn_km=300, warn_days=30, notes="Rider figure, not a maker's interval."),
    DefaultRule("POWER_PEDAL_BEARINGS", "Service pedal bearings", "POWER_METER_PEDALS", "PEDAL_SERVICE",
                interval_km=5000, interval_months=12, warn_km=300, warn_days=30,
                notes="No Favero interval found; riders regrease Assioma pedals about yearly or every 2,500 km."),
    DefaultRule("BB_CHECK", "Check bottom bracket", "BOTTOM_BRACKET", "BB_INSPECT", interval_km=6000,
                interval_months=12, warn_km=300, warn_days=30, notes="Personal value."),
    DefaultRule("BAR_TAPE_CHECK", "Inspect bar tape", "BAR_TAPE", "BAR_TAPE_INSPECT", interval_months=12,
                warn_days=30, reset_actions=("BAR_TAPE_INSPECT", "BAR_TAPE_REWRAP"), notes="Personal value."),
    DefaultRule("SEATPOST_PASTE", "Re-paste seatpost", "SEATPOST", "SEATPOST_SERVICE", interval_months=12,
                warn_days=30, notes="Stops a seatpost from seizing; personal value."),
    DefaultRule("HANGER_CHECK", "Check derailleur hanger", "DERAILLEUR_HANGER", "HANGER_ALIGN", interval_months=12,
                warn_days=30, notes="Also after every crash; personal value."),
    DefaultRule("CLEAT_CHECK", "Inspect cleats", "CLEATS", "CLEAT_INSPECT", interval_km=2000, warn_km=200,
                notes="Replace when a wear pad is worn through or clipping feels different, often about "
                      "6,000 km (rider figure; BikeRadar)."),
    DefaultRule("SHIFT_CABLE_CHECK", "Check shift cable", "SHIFT_CABLE", "CABLE_INSPECT", interval_km=5000,
                interval_months=12, warn_km=300, warn_days=30, requires_setup="MECHANICAL", notes="Personal value."),
    DefaultRule("SHIFT_HOUSING_CHECK", "Check shift housing", "SHIFT_HOUSING", "CABLE_INSPECT", interval_km=5000,
                interval_months=12, warn_km=300, warn_days=30, requires_setup="MECHANICAL", notes="Personal value."),
    # the whole bike
    DefaultRule("BIKE_TORQUE_CHECK", "Torque check", BIKE, "TORQUE_CHECK", interval_months=3, warn_days=14,
                notes="Every 3 months and once after the first ride on a newly fitted part (personal value). "
                      "Torque values come from each product's spec (torque_nm) where you entered it."),
    DefaultRule("BIKE_DI2_CHECK", "Di2 check (firmware, errors)", BIKE, "DI2_SYSTEM_CHECK", interval_months=6,
                warn_days=14, requires_setup="ELECTRONIC",
                notes="Firmware is updated with Shimano E-TUBE; 6 months is a personal value."),
    DefaultRule("BIKE_DI2_WIRES", "Inspect Di2 wires", BIKE, "DI2_WIRE_INSPECT", interval_months=12, warn_days=30,
                requires_setup="ELECTRONIC", notes="Personal value."),
    DefaultRule("BIKE_FULL_SERVICE", "Yearly full service", BIKE, "FULL_SERVICE", interval_months=12, warn_days=30,
                notes="Once a year, a full service of the whole bike: " + "; ".join(FULL_SERVICE_CHECKLIST)
                      + ". Personal value; each job keeps its own reminder."),
]


@dataclass(frozen=True)
class DefaultProfile:
    code: str
    name: str
    kind: str                       # OUTDOOR | TRAINER
    excluded_slots: tuple[str, ...] = ()
    excluded_types: tuple[str, ...] = ()
    notes: str = ""


DEFAULT_PROFILES: list[DefaultProfile] = [
    DefaultProfile("OUTDOOR", "Outdoor", "OUTDOOR"),
    DefaultProfile(
        "DIRECT_DRIVE_TRAINER", "Direct-drive trainer (wheels off)", "TRAINER",
        excluded_slots=("WHEELSET", "FRONT_WHEEL", "REAR_WHEEL", "CASSETTE"),
        excluded_types=("BRAKE_PADS", "TIRE", "BRAKE_ROTOR"),
        notes="Rear wheel and cassette are removed; the trainer has its own cassette. "
              "Front wheel, tires, rotors and pads do not wear.",
    ),
]

# How a bike shifts (bike.shifting). Not set: electronic when a Di2/AXS battery is fitted.
SHIFTING_TYPES: dict[str, str] = {"ELECTRONIC": "Electronic (Di2, AXS)", "MECHANICAL": "Mechanical (cables)"}

# How a wheel's tire is run (component.tire_setup on the wheel; tires inherit it from their wheel).
TIRE_SETUPS: dict[str, str] = {
    "TUBE": "Inner tube",
    "TUBELESS": "Tubeless (sealant)",
    "TUBULAR": "Tubular",
}
WHEEL_TYPES = ("FRONT_WHEEL", "REAR_WHEEL")

# Things that happen on a ride, logged as a journal issue linked to the ride and the affected part.
INCIDENT_TYPES: dict[str, str] = {
    "FLAT": "Flat tire",
    "CRASH": "Crash",
    "DEFECT": "Defect / mechanical",
    "OTHER": "Other incident",
}
# Ride conditions you set per ride (Strava does not provide them; imports never change them).
RIDE_CONDITIONS: dict[str, str] = {"DRY": "Dry", "WET": "Wet"}

RIDE_SPORT_TYPES = ("Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide")
