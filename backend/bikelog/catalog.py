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
    kind: str                       # LUBRICATE, INSPECT, MEASURE, SERVICE, CLEAN, REPAIR, CHARGE, NOTE
    targets: tuple[str, ...]        # component type codes, or ("*",) for all
    quick: bool = False             # offered as one-tap shortcut
    fields: tuple[str, ...] = ()    # extra inputs: symptom, work_done, outcome, measurement, consumable
    outcomes: tuple[str, ...] = ()  # allowed outcome codes (empty = free text)
    attention_outcomes: tuple[str, ...] = ()  # outcomes that need attention until a later event


POWER_METERS = ("POWER_METER", "POWER_METER_PEDALS")
# actions that charge a battery: a charge reminder needs one logged charge before it can count
CHARGE_ACTIONS = ("BATTERY_CHARGE", "POWER_CHARGE")

COMPONENT_TYPES: dict[str, ComponentType] = {t.code: t for t in [
    ComponentType("CHAIN", "Chain", "Drivetrain", ("CHAIN",)),
    ComponentType("QUICK_LINK", "Quick link", "Drivetrain", ("QUICK_LINK",), ("CHAIN",), removed_default="DISCARDED"),
    ComponentType("CASSETTE", "Cassette", "Drivetrain", ("CASSETTE",), ("REAR_WHEEL",)),
    ComponentType("CRANKSET", "Crankset", "Drivetrain", ("CRANKSET",)),
    ComponentType("CHAINRING", "Chainring", "Drivetrain", ("CHAINRING_OUTER", "CHAINRING_INNER"), ("CRANKSET",)),
    ComponentType("BOTTOM_BRACKET", "Bottom bracket", "Drivetrain", ("BOTTOM_BRACKET",)),
    ComponentType("REAR_DERAILLEUR", "Rear derailleur", "Drivetrain", ("REAR_DERAILLEUR",)),
    ComponentType("PULLEY_WHEEL", "Pulley wheel", "Drivetrain", ("PULLEY_UPPER", "PULLEY_LOWER"),
                  ("REAR_DERAILLEUR",), removed_default="DISCARDED"),
    ComponentType("FRONT_DERAILLEUR", "Front derailleur", "Drivetrain", ("FRONT_DERAILLEUR",)),
    # A wheelset holds the two wheels; the wheels hold tires, tubes, rotors, cassette, hub, spokes, rim tape.
    # Every part keeps its own km; moving the wheelset moves everything on it.
    ComponentType("WHEELSET", "Wheelset", "Wheels", ("WHEELSET",)),
    ComponentType("FRONT_WHEEL", "Front wheel", "Wheels", ("FRONT_WHEEL",), ("WHEELSET",)),
    ComponentType("REAR_WHEEL", "Rear wheel", "Wheels", ("REAR_WHEEL",), ("WHEELSET",)),
    ComponentType("HUB", "Hub", "Wheels", ("HUB",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("HUB_BEARINGS", "Hub bearings (set)", "Wheels", ("BEARINGS",), ("HUB",), removed_default="DISCARDED"),
    ComponentType("SPOKES", "Spokes (set)", "Wheels", ("SPOKES",), ("FRONT_WHEEL", "REAR_WHEEL")),
    ComponentType("RIM_TAPE", "Rim tape", "Wheels", ("RIM_TAPE",), ("FRONT_WHEEL", "REAR_WHEEL"),
                  removed_default="DISCARDED"),
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
    ComponentType("POWER_METER_PEDALS", "Power-meter pedals", "Contact points", ("PEDALS",)),
    ComponentType("SADDLE", "Saddle", "Contact points", ("SADDLE",)),
    ComponentType("SEATPOST", "Seatpost", "Contact points", ("SEATPOST",)),
    ComponentType("HANDLEBAR", "Handlebar", "Cockpit", ("HANDLEBAR",)),
    ComponentType("BAR_TAPE", "Bar tape", "Cockpit", ("BAR_TAPE",), removed_default="DISCARDED"),
    ComponentType("SHIFTERS", "Shifters", "Controls", ("SHIFTERS",)),
    ComponentType("BATTERY", "Battery (Di2/AXS)", "Electronics", ("BATTERY",)),
    # speed/cadence sensor: on a wheel (moves with the wheelset), on the crankset or on the bike
    ComponentType("SENSOR", "Sensor (speed/cadence)", "Electronics", ("SENSOR_SPEED", "SENSOR_CADENCE"),
                  ("FRONT_WHEEL", "REAR_WHEEL", "CRANKSET")),
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
    # cockpit
    Action("BAR_TAPE_REWRAP", "Rewrap bar tape (same tape)", "SERVICE", ("BAR_TAPE",), fields=("work_done",)),
    # generic
    Action("INSPECT", "Record inspection", "INSPECT", ALL, quick=True, fields=("outcome",),
           outcomes=("OK", "MONITOR", "WORN", "DAMAGE"), attention_outcomes=("MONITOR", "WORN", "DAMAGE")),
    Action("CLEAN", "Clean", "CLEAN", ALL),
    Action("SERVICE", "General service", "SERVICE", ALL, fields=("work_done",)),
    Action("REPAIR", "Repair", "REPAIR", ALL, fields=("symptom", "work_done", "outcome", "consumable")),
    Action("BATTERY_CHARGE", "Charged", "CHARGE", ("BATTERY",), quick=True),
]}


def action_applies(action: Action, component_type: str) -> bool:
    return action.targets == ALL or component_type in action.targets


@dataclass(frozen=True)
class DefaultRule:
    rule_code: str
    name: str
    component_type: str
    action_code: str
    trigger: str = "INTERVAL"                # INTERVAL | CYCLE_WINDOW | PARENT_COUNT
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
    requires_setup: str | None = None        # only when the part's wheel has this tire setup
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
    DefaultRule("TIRE_CHECK", "Inspect tire", "TIRE", "TIRE_INSPECT", interval_km=1000, warn_km=100),
    # sealant dries out with time, not distance; renewing it also resets the top-up reminder
    DefaultRule("TIRE_SEALANT", "Top up sealant", "TIRE", "SEALANT_TOP_UP", interval_months=3, warn_days=14,
                reset_actions=("SEALANT_TOP_UP", "SEALANT_RENEW"), requires_setup="TUBELESS"),
    DefaultRule("HEADSET_SERVICE", "Service headset", "HEADSET", "HEADSET_SERVICE",
                interval_km=5000, interval_months=12, warn_km=300, warn_days=30),
    # batteries (figures from retailer listings quoting the makers; not verified with the makers)
    DefaultRule("DI2_BATTERY_CHARGE", "Charge Di2 battery", "BATTERY", "BATTERY_CHARGE", interval_km=800, warn_km=100,
                notes="Shimano BT-DN300: about 1000 km per charge (less with much front shifting); 800 km leaves a "
                      "margin. Source: retailer listings (Rose, Tweeks), not verified with Shimano."),
    DefaultRule("POWER_METER_CHARGE", "Charge power meter", "POWER_METER", "POWER_CHARGE", interval_hours=50,
                warn_hours=10, notes="Set to your power meter's battery life with a margin."),
    DefaultRule("POWER_PEDALS_CHARGE", "Charge power-meter pedals", "POWER_METER_PEDALS", "POWER_CHARGE",
                interval_hours=50, warn_hours=10,
                notes="Favero Assioma PRO RS-1: at least 60 h per charge (up to about 160 h after a firmware "
                      "update). 50 h leaves a margin. Source: retailer listings quoting Favero, not verified."),
    DefaultRule("SENSOR_BATTERY", "Replace sensor battery", "SENSOR", "COIN_CELL_REPLACE", interval_hours=400,
                warn_hours=40, interval_months=12, warn_days=30,
                notes="Magene S3+ (CR2032): about 500 h of riding per battery (retailer listings, not verified with "
                      "Magene); 400 h leaves a margin. 12 months covers standby drain (your estimate)."),
    DefaultRule("SHIFTER_COIN_CELLS", "Replace shifter coin cells", "SHIFTERS", "COIN_CELL_REPLACE",
                interval_months=24, warn_days=30, active=False,
                notes="Wireless Di2 levers (CR1632): about 2 years. Off by default (mechanical shifters have no "
                      "battery); switch it on for wireless levers."),
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
                requires_setup="TUBELESS", notes="Tubeless only: check at every tire change or yearly."),
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
