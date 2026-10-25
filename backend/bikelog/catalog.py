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


@dataclass(frozen=True)
class Action:
    code: str
    name: str
    kind: str                       # LUBRICATE, INSPECT, MEASURE, SERVICE, CLEAN, REPAIR, NOTE
    targets: tuple[str, ...]        # component type codes, or ("*",) for all
    quick: bool = False             # offered as one-tap shortcut
    fields: tuple[str, ...] = ()    # extra inputs: symptom, work_done, outcome, measurement, consumable
    outcomes: tuple[str, ...] = ()  # allowed outcome codes (empty = free text)
    attention_outcomes: tuple[str, ...] = ()  # outcomes that need attention until a later event


COMPONENT_TYPES: dict[str, ComponentType] = {t.code: t for t in [
    ComponentType("CHAIN", "Chain", "Drivetrain", ("CHAIN",)),
    ComponentType("QUICK_LINK", "Quick link", "Drivetrain", ("QUICK_LINK",), ("CHAIN",), removed_default="DISCARDED"),
    ComponentType("CASSETTE", "Cassette", "Drivetrain", ("CASSETTE",), ("REAR_WHEEL",)),
    ComponentType("CRANKSET", "Crankset", "Drivetrain", ("CRANKSET",)),
    ComponentType("CHAINRING", "Chainring", "Drivetrain", ("CHAINRING_OUTER", "CHAINRING_INNER"), ("CRANKSET",)),
    ComponentType("BOTTOM_BRACKET", "Bottom bracket", "Drivetrain", ("BOTTOM_BRACKET",)),
    ComponentType("REAR_DERAILLEUR", "Rear derailleur", "Drivetrain", ("REAR_DERAILLEUR",)),
    ComponentType("FRONT_DERAILLEUR", "Front derailleur", "Drivetrain", ("FRONT_DERAILLEUR",)),
    ComponentType("FRONT_WHEEL", "Front wheel", "Wheels", ("FRONT_WHEEL",)),
    ComponentType("REAR_WHEEL", "Rear wheel", "Wheels", ("REAR_WHEEL",)),
    ComponentType("TIRE", "Tire", "Wheels", ("TIRE",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("INNER_TUBE", "Inner tube", "Wheels", ("TUBE",), ("FRONT_WHEEL", "REAR_WHEEL"),
                  removed_default="AWAITING_SERVICE"),
    ComponentType("BRAKE_ROTOR", "Brake rotor", "Brakes", ("ROTOR",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("BRAKE_CIRCUIT", "Brake circuit (hydraulic)", "Brakes", ("FRONT_BRAKE", "REAR_BRAKE"),
                  tracks_distance=True),
    ComponentType("BRAKE_PADS", "Brake pads", "Brakes", ("FRONT_PADS", "REAR_PADS"), removed_default="DISCARDED"),
    ComponentType("POWER_METER", "Power meter", "Drivetrain", ("POWER_METER",), ("CRANKSET",)),
    ComponentType("HEADSET", "Headset", "Frame", ("HEADSET",)),
    ComponentType("PEDALS", "Pedals", "Contact points", ("PEDALS",)),
    ComponentType("SADDLE", "Saddle", "Contact points", ("SADDLE",)),
    ComponentType("SEATPOST", "Seatpost", "Contact points", ("SEATPOST",)),
    ComponentType("HANDLEBAR", "Handlebar", "Cockpit", ("HANDLEBAR",)),
    ComponentType("BAR_TAPE", "Bar tape", "Cockpit", ("BAR_TAPE",), removed_default="DISCARDED"),
    ComponentType("SHIFTERS", "Shifters", "Controls", ("SHIFTERS",)),
    ComponentType("BATTERY", "Battery (Di2/AXS)", "Electronics", ("BATTERY",)),
    ComponentType("OTHER", "Other part", "Other", ()),
]}

ALL = ("*",)

# What happened to an item that is no longer installed. RETIRED, DISCARDED and SOLD take it out of
# use (component.status = RETIRED); its record, mileage and history are always kept.
DISPOSITIONS: dict[str, str] = {
    "STORED": "Stored as a reusable spare",
    "AWAITING_SERVICE": "Awaiting inspection or repair",
    "RETIRED": "Retired from use",
    "DISCARDED": "Discarded",
    "SOLD": "Sold or given away",
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
           attention_outcomes=("APPROACHING_LIMIT", "AT_LIMIT")),
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
           attention_outcomes=("LOW", "AT_LIMIT")),
    Action("ROTOR_MEASURE", "Measure rotor thickness", "MEASURE", ("BRAKE_ROTOR",),
           fields=("measurement", "outcome"), outcomes=("OK", "AT_LIMIT"), attention_outcomes=("AT_LIMIT",)),
    # wheels: inspection, hub bearings and freehub are deliberately separate actions
    Action("WHEEL_INSPECT", "Inspect wheel (trueness, spokes, rim)", "INSPECT", ("FRONT_WHEEL", "REAR_WHEEL"),
           quick=True, fields=("outcome",), outcomes=("OK", "OUT_OF_TRUE", "DAMAGE"),
           attention_outcomes=("OUT_OF_TRUE", "DAMAGE")),
    Action("WHEEL_TRUE", "True wheel", "SERVICE", ("FRONT_WHEEL", "REAR_WHEEL")),
    Action("HUB_BEARING_SERVICE", "Service hub bearings", "SERVICE", ("FRONT_WHEEL", "REAR_WHEEL"),
           fields=("work_done", "consumable")),
    Action("FREEHUB_SERVICE", "Service freehub", "SERVICE", ("REAR_WHEEL",), fields=("work_done", "consumable")),
    # tires
    Action("SEALANT_TOP_UP", "Top up sealant", "SERVICE", ("TIRE",), quick=True, fields=("consumable",)),
    Action("SEALANT_RENEW", "Renew sealant", "SERVICE", ("TIRE",), fields=("consumable",)),
    Action("TIRE_INSPECT", "Inspect tire", "INSPECT", ("TIRE",), quick=True,
           fields=("outcome",), outcomes=("OK", "CUT", "WORN"), attention_outcomes=("CUT", "WORN")),
    Action("TUBE_PATCH", "Patch tube", "REPAIR", ("INNER_TUBE",), fields=("symptom", "outcome", "consumable"),
           outcomes=("REPAIRED", "NOT_REPAIRABLE")),
    # headset and power meter
    Action("HEADSET_SERVICE", "Service headset (clean, grease, check play)", "SERVICE", ("HEADSET",),
           fields=("symptom", "work_done", "outcome", "consumable")),
    Action("POWER_ZERO_OFFSET", "Zero offset / calibrate power meter", "SERVICE", ("POWER_METER",), quick=True),
    Action("POWER_BATTERY", "Charge / replace power-meter battery", "SERVICE", ("POWER_METER",), quick=True,
           fields=("consumable",)),
    Action("POWER_FIRMWARE", "Update power-meter firmware", "SERVICE", ("POWER_METER",), fields=("work_done",)),
    # cockpit
    Action("BAR_TAPE_REWRAP", "Rewrap bar tape (same tape)", "SERVICE", ("BAR_TAPE",), fields=("work_done",)),
    # generic
    Action("INSPECT", "Record inspection", "INSPECT", ALL, quick=True, fields=("outcome",),
           outcomes=("OK", "MONITOR", "WORN", "DAMAGE"), attention_outcomes=("MONITOR", "WORN", "DAMAGE")),
    Action("CLEAN", "Clean", "CLEAN", ALL),
    Action("SERVICE", "General service", "SERVICE", ALL, fields=("work_done",)),
    Action("REPAIR", "Repair", "REPAIR", ALL, fields=("symptom", "work_done", "outcome", "consumable")),
    Action("BATTERY_CHARGE", "Charge battery", "SERVICE", ("BATTERY",), quick=True),
]}


def action_applies(action: Action, component_type: str) -> bool:
    return action.targets == ALL or component_type in action.targets


@dataclass(frozen=True)
class DefaultRule:
    rule_code: str
    name: str
    component_type: str
    action_code: str
    trigger: str = "INTERVAL"                # INTERVAL | CYCLE_WINDOW
    interval_km: float | None = None
    interval_months: int | None = None
    window_min_km: float | None = None
    window_max_km: float | None = None
    cycle_action_code: str | None = None     # CYCLE_WINDOW: action that starts a new cycle
    reset_actions: tuple[str, ...] = ()      # default: (action_code,)
    warn_km: float | None = None
    warn_days: int | None = None
    origin: str = "DEFAULT"
    requires_setup: str | None = None        # only when the part's wheel has this tire setup


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
    DefaultRule("TIRE_CHECK", "Inspect tire", "TIRE", "TIRE_INSPECT", interval_km=1000, warn_km=100),
    # sealant dries out with time, not distance; renewing it also resets the top-up reminder
    DefaultRule("TIRE_SEALANT", "Top up sealant", "TIRE", "SEALANT_TOP_UP", interval_months=3, warn_days=14,
                reset_actions=("SEALANT_TOP_UP", "SEALANT_RENEW"), requires_setup="TUBELESS"),
    DefaultRule("HEADSET_SERVICE", "Service headset", "HEADSET", "HEADSET_SERVICE",
                interval_km=5000, interval_months=12, warn_km=300, warn_days=30),
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
        excluded_slots=("FRONT_WHEEL", "REAR_WHEEL", "CASSETTE"),
        excluded_types=("BRAKE_PADS", "TIRE", "BRAKE_ROTOR"),
        notes="Rear wheel and cassette are removed; the trainer has its own cassette. "
              "Front wheel, tires, rotors and pads do not wear.",
    ),
]

# How a wheel's tire is run (component.tire_setup on the wheel; tires inherit it from their wheel).
TIRE_SETUPS: dict[str, str] = {
    "TUBE": "Inner tube",
    "TUBELESS": "Tubeless (sealant)",
    "TUBULAR": "Tubular",
}
WHEEL_TYPES = ("FRONT_WHEEL", "REAR_WHEEL")

RIDE_SPORT_TYPES = ("Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide")
