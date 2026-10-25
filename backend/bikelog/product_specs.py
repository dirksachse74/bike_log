"""Spec fields per component type, used by the JSON import templates (one template per type).

Each field: (key, kind, description, unit or enum). kinds: "string", "integer", "number", "boolean",
"enum". Fields are optional: a scraper fills what it finds. Spec keys not listed here are still
imported (and reported as extra), so a template never blocks useful data.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecField:
    key: str
    kind: str
    description: str
    unit: str | None = None
    values: tuple[str, ...] = ()
    example: object = None


def F(key, kind, description, unit=None, values=(), example=None):  # noqa: N802 - table helper
    return SpecField(key, kind, description, unit, tuple(values), example)


COMMON = [
    F("weight_g", "number", "Weight", "g", example=250),
    F("color", "string", "Colour / finish"),
    F("material", "string", "Main material"),
]

SPEEDS = F("speeds", "integer", "Number of rear sprockets the part is made for", example=12)

SPEC_FIELDS: dict[str, list[SpecField]] = {
    "CHAIN": [SPEEDS, F("links", "integer", "Links as sold", example=116),
              F("joining", "string", "Joining method", example="quick link SM-CN910-12"),
              F("compatibility", "string", "Drivetrain standard", example="Shimano Hyperglide+")],
    "QUICK_LINK": [SPEEDS, F("reusable", "boolean", "Maker allows reuse after opening", example=False),
                   F("pieces_per_pack", "integer", "Connectors per package", example=2)],
    "CASSETTE": [SPEEDS, F("range", "string", "Smallest-largest sprocket", example="11-34"),
                 F("sprockets", "string", "All sprockets", example="11-12-13-14-15-17-19-21-24-27-30-34"),
                 F("freehub", "string", "Freehub standard", example="Shimano HG 11-speed road")],
    "CRANKSET": [SPEEDS, F("crank_length_mm", "number", "Crank arm length", "mm", example=172.5),
                 F("chainrings", "string", "Chainring teeth", example="52-36"),
                 F("bcd_mm", "number", "Bolt circle diameter", "mm", example=110),
                 F("spindle", "string", "Spindle standard", example="Hollowtech II 24 mm"),
                 F("power_meter", "boolean", "Has a built-in power meter", example=False)],
    "CHAINRING": [SPEEDS, F("teeth", "integer", "Number of teeth", example=52),
                  F("position", "enum", "Position on the crank", values=("outer", "inner", "single"), example="outer"),
                  F("bcd_mm", "number", "Bolt circle diameter", "mm", example=110)],
    "BOTTOM_BRACKET": [F("standard", "string", "Shell standard", example="BSA 68 mm threaded"),
                       F("spindle_mm", "number", "Spindle diameter", "mm", example=24)],
    "REAR_DERAILLEUR": [SPEEDS, F("max_cog", "integer", "Largest sprocket", "T", example=34),
                        F("capacity", "integer", "Total capacity", "T", example=39),
                        F("electronic", "boolean", "Electronic shifting", example=True),
                        F("mount", "string", "Mount", example="standard hanger")],
    "FRONT_DERAILLEUR": [SPEEDS, F("max_chainring", "integer", "Largest chainring", "T", example=52),
                         F("capacity", "integer", "Front capacity", "T", example=16),
                         F("electronic", "boolean", "Electronic shifting", example=True),
                         F("mount", "enum", "Mount", values=("braze-on", "clamp"), example="braze-on")],
    "FRONT_WHEEL": [F("rim_depth_mm", "number", "Rim depth", "mm", example=45),
                    F("internal_width_mm", "number", "Internal rim width", "mm", example=21),
                    F("tubeless", "boolean", "Tubeless ready", example=True),
                    F("axle", "string", "Axle standard", example="12x100 thru axle"),
                    F("brake", "enum", "Brake type", values=("disc", "rim"), example="disc"),
                    F("rotor_mount", "enum", "Rotor mount", values=("centerlock", "6-bolt", "none"),
                      example="centerlock"),
                    F("spokes", "integer", "Spoke count", example=24)],
    "REAR_WHEEL": [F("rim_depth_mm", "number", "Rim depth", "mm", example=45),
                   F("internal_width_mm", "number", "Internal rim width", "mm", example=21),
                   F("tubeless", "boolean", "Tubeless ready", example=True),
                   F("axle", "string", "Axle standard", example="12x142 thru axle"),
                   F("brake", "enum", "Brake type", values=("disc", "rim"), example="disc"),
                   F("rotor_mount", "enum", "Rotor mount", values=("centerlock", "6-bolt", "none"),
                     example="centerlock"),
                   F("freehub", "string", "Freehub body", example="Shimano HG 11/12-speed road"),
                   F("spokes", "integer", "Spoke count", example=24)],
    "TIRE": [F("size", "string", "Size as printed", example="700x28c"),
             F("etrto", "string", "ETRTO size", example="28-622"),
             F("tubeless", "boolean", "Tubeless ready", example=True),
             F("tpi", "integer", "Casing threads per inch", example=120),
             F("compound", "string", "Rubber compound", example="BlackChili")],
    "INNER_TUBE": [F("size", "string", "Size range", example="700x23-32c"),
                   F("valve", "enum", "Valve type", values=("presta", "schrader", "dunlop"), example="presta"),
                   F("valve_length_mm", "number", "Valve length", "mm", example=60),
                   F("tube_material", "enum", "Tube material", values=("butyl", "latex", "TPU"), example="TPU")],
    "BRAKE_ROTOR": [F("diameter_mm", "number", "Diameter", "mm", example=160),
                    F("mount", "enum", "Mount", values=("centerlock", "6-bolt"), example="centerlock"),
                    F("thickness_mm", "number", "Thickness when new", "mm", example=1.8),
                    F("min_thickness_mm", "number", "Minimum thickness (replace below)", "mm", example=1.5)],
    "BRAKE_CIRCUIT": [F("caliper", "string", "Caliper model", example="BR-R8170"),
                      F("lever", "string", "Lever model", example="ST-R8170"),
                      F("hose", "string", "Hose model", example="SM-BH90-JK-SSR"),
                      F("fluid", "enum", "Brake fluid", values=("mineral oil", "DOT 4", "DOT 5.1"),
                        example="mineral oil"),
                      F("mount", "enum", "Caliper mount", values=("flat mount", "post mount", "rim"),
                        example="flat mount")],
    "BRAKE_PADS": [F("compound", "enum", "Pad compound", values=("resin", "metal", "semi-metal", "rim"),
                     example="resin"),
                   F("cooling_fins", "boolean", "Has cooling fins", example=True),
                   F("fits", "string", "Calipers it fits", example="BR-R8170, BR-R9270"),
                   F("min_thickness_mm", "number", "Replace below this pad thickness", "mm", example=0.5)],
    "HEADSET": [F("standard", "string", "Headset standard (SHIS), top / bottom", example="ZS44/28.6 | ZS56/40"),
                F("steerer", "string", "Steerer tube", example="1-1/8\" to 1.5\" tapered"),
                F("bearings", "string", "Bearing type and size", example="cartridge 41.8 mm 45x45"),
                F("integrated_cables", "boolean", "Routes hoses/cables through the headset", example=False)],
    "POWER_METER": [F("placement", "enum", "Where it measures",
                      values=("left crank", "dual crank", "spider", "pedals", "hub", "chainring"), example="spider"),
                    F("sides", "enum", "Measures one or both legs", values=("single", "dual"), example="dual"),
                    F("accuracy_pct", "number", "Claimed accuracy", "±%", example=1.5),
                    F("battery", "string", "Battery", example="rechargeable, USB-C"),
                    F("battery_life_h", "number", "Claimed battery life", "h", example=300),
                    F("protocols", "string", "Wireless protocols", example="ANT+, Bluetooth"),
                    F("crank_length_mm", "number", "Crank length (crank-based meters)", "mm", example=172.5),
                    F("spindle", "string", "Spindle / interface it fits", example="Shimano Hollowtech II")],
    "PEDALS": [F("system", "string", "Cleat system", example="SPD-SL"),
               F("q_factor_mm", "number", "Q-factor", "mm", example=53),
               F("power_meter", "boolean", "Has a built-in power meter", example=False)],
    "SADDLE": [F("width_mm", "number", "Width", "mm", example=143),
               F("length_mm", "number", "Length", "mm", example=245),
               F("rails", "string", "Rail material / shape", example="carbon 7x9 mm")],
    "SEATPOST": [F("diameter_mm", "number", "Diameter", "mm", example=27.2),
                 F("length_mm", "number", "Length", "mm", example=350),
                 F("offset_mm", "number", "Setback", "mm", example=15)],
    "HANDLEBAR": [F("width_mm", "number", "Width", "mm", example=420),
                  F("reach_mm", "number", "Reach", "mm", example=80),
                  F("drop_mm", "number", "Drop", "mm", example=125),
                  F("clamp_mm", "number", "Stem clamp diameter", "mm", example=31.8),
                  F("integrated", "boolean", "One-piece bar and stem", example=False)],
    "BAR_TAPE": [F("thickness_mm", "number", "Thickness", "mm", example=2.5),
                 F("length_mm", "number", "Length per side", "mm", example=2000)],
    "SHIFTERS": [SPEEDS, F("electronic", "boolean", "Electronic shifting", example=True),
                 F("brake_type", "enum", "Brake type", values=("hydraulic disc", "mechanical disc", "rim"),
                   example="hydraulic disc"),
                 F("power", "string", "Power source", example="CR1632 coin cell")],
    "BATTERY": [F("system", "string", "Shifting system", example="Shimano Di2"),
                F("capacity_wh", "number", "Capacity", "Wh", example=3.7),
                F("mount", "string", "Where it is mounted", example="internal, seatpost")],
    "WHEELSET": [F("rim_depth_mm", "number", "Rim depth", "mm", example=50),
                 F("internal_width_mm", "number", "Internal rim width", "mm", example=21),
                 F("brake", "enum", "Brake type", values=("disc", "rim"), example="disc"),
                 F("axles", "string", "Axle standard front / rear", example="12x100 / 12x142 thru-axle"),
                 F("weight_g", "number", "Weight of the pair", "g", example=1450)],
    "HUB": [F("axle", "string", "Axle standard", example="12x142 thru-axle"),
            F("freehub", "string", "Freehub body (rear)", example="Shimano HG / Microspline"),
            F("rotor_mount", "enum", "Rotor mount", values=("center lock", "6-bolt"), example="center lock"),
            F("spoke_holes", "number", "Spoke holes", example=24)],
    "HUB_BEARINGS": [F("size", "string", "Bearing size(s)", example="6902 2RS x2"),
                     F("type", "enum", "Bearing type", values=("cartridge", "cup and cone", "ceramic"),
                       example="cartridge")],
    "SPOKES": [F("count", "number", "Number of spokes", example=24),
               F("model", "string", "Spoke model and length", example="DT Aerolite 286 mm"),
               F("nipples", "string", "Nipples", example="alloy, 14 mm")],
    "RIM_TAPE": [F("width_mm", "number", "Width", "mm", example=25)],
    "PULLEY_WHEEL": [SPEEDS, F("teeth", "number", "Teeth", example=13),
                     F("bearing", "string", "Bearing", example="cartridge")],
    "POWER_METER_PEDALS": [F("system", "string", "Cleat system", example="Shimano SPD-SL"),
                           F("sides", "enum", "Measures one or both legs", values=("single", "dual"),
                             example="dual"),
                           F("battery", "string", "Battery", example="rechargeable, magnetic charger"),
                           F("battery_life_h", "number", "Claimed battery life", "h", example=60),
                           F("protocols", "string", "Wireless protocols", example="ANT+, Bluetooth")],
    "SENSOR": [F("kind", "enum", "Sensor kind", values=("speed", "cadence", "speed/cadence"), example="speed"),
               F("battery", "string", "Battery", example="CR2032"),
               F("battery_life_h", "number", "Claimed battery life", "h", example=500),
               F("protocols", "string", "Wireless protocols", example="ANT+, Bluetooth")],
    "OTHER": [],
}


def fields_for(component_type: str) -> list[SpecField]:
    return SPEC_FIELDS.get(component_type, []) + COMMON
