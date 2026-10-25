"""SRAM road and gravel groupsets, 12 and 13 speed, hydraulic disc brakes (SRAM calls them HRD):
RED AXS E1 2×12, Force AXS 2×12, Rival AXS 2×12, Apex XPLR 1×12 (AXS or mechanical), and the 13-speed 1×
gravel groups RED XPLR AXS and Force XPLR AXS (E1).

Data from retailer listings, reviews and SRAM support articles found on 2026-10-26 (tunecycles.com.au,
bike-components.de, bike24.com, rosebikes, merlincycles.com, decathlon.co.uk, bikerumor.com, bikeradar.com,
cyclingnews.com, support.sram.com). sram.com product pages were not reachable from the build environment and
retailers disagree on some codes, so models are named as SRAM sells them (e.g. "RED AXS E1 rear derailleur")
rather than by part number, and every template is marked unverified until checked against
https://www.sram.com/en/service (spec sheets and compatibility maps).

AXS: wireless levers on CR2032 coin cells; each derailleur carries its own AXS battery (charge reminder in ride
hours, see _shared.AXS_BATTERY_RULE). XDR driver body needed for the 10-tooth cassettes.
"""
from bikelog.groupset_templates._shared import (
    axs_batteries, bb_option, bottom_bracket, brakes, cassette_option, chain, chainring_1x, chainrings_2x,
    crank_length_option, gearing_option, pads, pulleys, ring_option, rotor_options, rotors, shift_cables,
)

SOURCE = ("Retailer listings, reviews and SRAM support articles (tunecycles.com.au, bike-components.de, bike24.com, "
          "rosebikes, merlincycles.com, bikerumor.com, bikeradar.com, cyclingnews.com, support.sram.com), "
          "2026-10-26; not yet checked against SRAM's own spec sheets")
DUB_BB = bb_option([("BSA", "Threaded BSA 68 mm (DUB BSA)", "SRAM DUB BSA road bottom bracket",
                     "BSA threaded, 68 mm shell"),
                    ("PF", "Press-fit (DUB PF86 / BB92)", "SRAM DUB PressFit road bottom bracket",
                     "Press-fit 86.5 / 92 mm")], "BSA")
SPROCKETS_12 = {"10-28": "10-11-12-13-14-15-16-17-19-21-24-28",
                "10-30": "10-11-12-13-14-15-17-19-21-24-27-30",
                "10-33": "10-11-12-13-14-15-17-19-21-24-28-33",
                "10-36": "10-12-13-14-15-17-19-21-24-28-32-36"}
SPROCKETS_13 = {"10-46": "10-11-12-13-15-17-19-21-24-28-32-38-46"}


def _lever(series: str, specs_extra: dict | None = None) -> dict:
    return {"key": "shifters", "type": "SHIFTERS", "name": "AXS levers", "model": f"{series} AXS HRD shift-brake levers",
            "specs": {"function": "Wireless AXS shift-brake levers, hydraulic disc brake",
                      "power": "CR2032 coin cell in each lever", "brake fluid": "DOT 5.1", **(specs_extra or {})},
            "mount": {"slot": "SHIFTERS"}}


def _drivetrain_2x(series: str, chain_model: str, rotor_model: str, *, max_cog: str,
                   ring_model: str, crank_model: str) -> list[dict]:
    return [
        _lever(series),
        {"key": "front_derailleur", "type": "FRONT_DERAILLEUR", "name": "front derailleur",
         "model": f"{series} AXS front derailleur", "specs": {"speeds": "2×12", "mount": "Braze-on"},
         "mount": {"slot": "FRONT_DERAILLEUR"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur",
         "model": f"{series} AXS rear derailleur", "specs": {"speeds": "12", "max low sprocket": f"{max_cog}T"},
         "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys(f"{series} AXS rear derailleur", "12"),
        *axs_batteries(front=True),
        {"key": "crankset", "type": "CRANKSET", "name": "crankset", "model": crank_model + " {crank_length} mm",
         "specs": {"speeds": "2×12", "crank length": "{crank_length} mm", "chainrings": "{outer}-{inner}T",
                   "spindle": "DUB (28.99 mm)", "power meter": "{power_meter}"},
         "mount": {"slot": "CRANKSET"}},
        *chainrings_2x(ring_model),
        bottom_bracket("DUB (28.99 mm)"),
        {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
         "specs": {"speeds": "12", "range": "{cassette}T", "sprockets": "{sprockets}", "freehub": "SRAM XDR"},
         "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
        *chain(chain_model, {"speeds": "12 (Flattop)", "joining": "Flattop PowerLock"},
               "SRAM Flattop PowerLock", {"speeds": "12", "reuse": "SRAM: single use, fit a new one after opening"}),
        *brakes(f"{series} AXS HRD caliper", {"caliper": "Flat mount, 2 pistons", "fluid": "DOT 5.1",
                                              "rotor": "140 / 160 mm"}),
        *pads("SRAM road disc brake pads (organic)", {"compound": "Organic", "fits": f"{series} HRD calipers"}),
        *rotors(rotor_model + " {size} mm", {"mount": "Center Lock or 6-bolt (check your hubs)"}),
    ]


def _power_option(plain: str, power: str) -> dict:
    return {"key": "power_meter", "label": "Crankset", "default": "NO",
            "choices": [{"value": "NO", "label": plain, "vars": {"power_meter": "none"}},
                        {"value": "YES", "label": power, "vars": {"power_meter": "built-in spindle/spider power meter"}}]}


def _template(code, name, series, prefix, notes, options, items_) -> dict:
    return {"code": code, "name": name, "maker": "SRAM", "series": series, "label_prefix": prefix,
            "speeds": 13 if "13" in name.split("·")[1] else 12, "source": SOURCE, "checked_on": "2026-10-26",
            "verified": False, "notes": notes, "options": options, "items": items_}


RED_E1 = _template(
    "SRAM_RED_AXS_E1_2X12", "SRAM RED AXS E1 · 2×12 · hydraulic disc", "RED AXS E1", "RED",
    "2024 RED AXS (E1). Rear derailleur up to 36T. Each derailleur has its own AXS battery.",
    [crank_length_option(("160", "165", "167.5", "170", "172.5", "175")),
     gearing_option([("46", "33", ""), ("48", "35", ""), ("50", "37", "")], "48-35"),
     _power_option("RED E1 carbon crankset", "RED E1 power meter crankset"),
     cassette_option(SPROCKETS_12, "10-33", "RED XG-1290 E1 {cassette}"),
     *rotor_options(), DUB_BB],
    _drivetrain_2x("RED E1", "RED E1 Flattop chain", "SRAM Paceline X", max_cog="36",
                   ring_model="RED E1 chainring {teeth}T", crank_model="RED E1 crankset"))

FORCE = _template(
    "SRAM_FORCE_AXS_2X12", "SRAM Force AXS · 2×12 · hydraulic disc", "Force AXS", "Force",
    "Force AXS (2023 D2 generation). Rear derailleur up to 36T. Each derailleur has its own AXS battery.",
    [crank_length_option(("160", "165", "167.5", "170", "172.5", "175")),
     gearing_option([("46", "33", ""), ("48", "35", "")], "48-35"),
     _power_option("Force crankset", "Force power meter crankset"),
     cassette_option(SPROCKETS_12, "10-33", "Force XG-1270 {cassette}"),
     *rotor_options(), DUB_BB],
    _drivetrain_2x("Force", "Force Flattop chain", "SRAM CenterLine XR", max_cog="36",
                   ring_model="Force chainring {teeth}T", crank_model="Force crankset"))

RIVAL = _template(
    "SRAM_RIVAL_AXS_2X12", "SRAM Rival AXS · 2×12 · hydraulic disc", "Rival AXS", "Rival",
    "Rival AXS. Rear derailleur up to 36T. Each derailleur has its own AXS battery.",
    [crank_length_option(("160", "165", "167.5", "170", "172.5", "175")),
     gearing_option([("46", "33", ""), ("48", "35", "")], "46-33"),
     _power_option("Rival crankset", "Rival power meter crankset (left side)"),
     cassette_option({k: v for k, v in SPROCKETS_12.items() if k in ("10-30", "10-36")}, "10-36",
                     "Rival XG-1250 {cassette}"),
     *rotor_options(), DUB_BB],
    _drivetrain_2x("Rival", "Rival Flattop chain", "SRAM CenterLine", max_cog="36",
                   ring_model="Rival chainring {teeth}T", crank_model="Rival crankset"))


def _xplr13(code, series, prefix, cassette_model, rd_model):
    return _template(
        code, f"SRAM {series} AXS · 1×13 · hydraulic disc (gravel)", f"{series} AXS 13-speed", prefix,
        "13-speed 1× gravel group. The full-mount rear derailleur needs a UDH frame (SRAM: chainstay 415 mm or "
        "longer, 47.5 mm chainline) and only works with the 10-46 XPLR 13-speed cassette and Flattop chains. "
        "One AXS battery, on the rear derailleur.",
        [crank_length_option(("160", "165", "167.5", "170", "172.5", "175")),
         ring_option(["38", "40", "42", "44", "46"], "42"),
         cassette_option(SPROCKETS_13, "10-46", cassette_model),
         *rotor_options(front="160", rear="160"), DUB_BB],
        [
            _lever(series.split()[0] if series.startswith("RED") else "Force",
                   {"note": "Same levers as the 2× road group; the left lever's button shifts down on 1×"}),
            {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": rd_model,
             "specs": {"speeds": "13", "mount": "Full mount (UDH)", "cassette": "XPLR 10-46 only"},
             "mount": {"slot": "REAR_DERAILLEUR"}},
            *pulleys(rd_model, "12", speeds="13"),
            *axs_batteries(front=False),
            {"key": "crankset", "type": "CRANKSET", "name": "crankset",
             "model": f"{series} crankset 1× " + "{crank_length} mm",
             "specs": {"speeds": "1×13", "crank length": "{crank_length} mm", "chainring": "{ring}T",
                       "spindle": "DUB (28.99 mm)", "chainline": "47.5 mm"},
             "mount": {"slot": "CRANKSET"}},
            chainring_1x(f"{series} X-Sync chainring " + "{ring}T"),
            bottom_bracket("DUB (28.99 mm)"),
            {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
             "specs": {"speeds": "13", "range": "{cassette}T", "sprockets": "{sprockets}", "freehub": "SRAM XDR"},
             "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
            *chain(f"{prefix} Flattop chain 12/13-speed", {"speeds": "12/13 (Flattop)", "joining": "Flattop PowerLock"},
                   "SRAM Flattop PowerLock", {"speeds": "12/13", "reuse": "SRAM: single use, fit a new one after opening"}),
            *brakes(f"{prefix} AXS HRD caliper", {"caliper": "Flat mount, 2 pistons", "fluid": "DOT 5.1",
                                                  "rotor": "160 mm"}),
            *pads("SRAM road disc brake pads (organic)", {"compound": "Organic", "fits": f"{prefix} HRD calipers"}),
            *rotors("SRAM Paceline X {size} mm" if prefix == "RED" else "SRAM CenterLine XR {size} mm",
                    {"mount": "Center Lock or 6-bolt (check your hubs)"}),
        ])


RED_XPLR_13 = _xplr13("SRAM_RED_XPLR_AXS_1X13", "RED XPLR", "RED", "RED XPLR XG-1391 E1 {cassette}",
                      "RED XPLR AXS rear derailleur")
FORCE_XPLR_13 = _xplr13("SRAM_FORCE_XPLR_AXS_1X13", "Force XPLR", "Force", "Force XPLR XG-1371 E1 {cassette}",
                        "Force XPLR AXS rear derailleur")

APEX_XPLR = _template(
    "SRAM_APEX_XPLR_1X12", "SRAM Apex XPLR · 1×12 · hydraulic disc", "Apex XPLR", "Apex",
    "Entry-level 1× group, wireless (AXS) or with cables. The 11-44 XPLR cassette fits a standard 11-speed "
    "freehub. For the mechanical version set the bike's shifting to Mechanical so the cable reminders apply.",
    [{"key": "shifting", "label": "Shifting", "default": "AXS",
      "choices": [{"value": "AXS", "label": "AXS (wireless)",
                   "vars": {"lever_model": "Apex AXS HRD shift-brake levers", "rd_model": "Apex XPLR AXS rear derailleur",
                            "lever_power": "CR2032 coin cell in the right lever"}},
                  {"value": "MECH", "label": "Mechanical (cable)",
                   "vars": {"lever_model": "Apex 1 HRD shift-brake levers", "rd_model": "Apex XPLR rear derailleur",
                            "lever_power": "none (cable)"}}]},
     crank_length_option(("165", "170", "172.5", "175")),
     ring_option(["38", "40", "42"], "40"),
     cassette_option({"11-44": "11-13-15-17-19-21-24-28-32-36-40-44"}, "11-44", "Apex XPLR PG-1231 {cassette}"),
     *rotor_options(front="160", rear="160"), DUB_BB],
    [
        {"key": "shifters", "type": "SHIFTERS", "name": "levers", "model": "{lever_model}",
         "specs": {"function": "1×12 shift-brake lever right, brake lever left, hydraulic disc",
                   "power": "{lever_power}", "brake fluid": "DOT 5.1"},
         "mount": {"slot": "SHIFTERS"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": "{rd_model}",
         "specs": {"speeds": "12", "max low sprocket": "44T", "clutch": "yes"}, "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys("Apex XPLR rear derailleur", "12"),
        {**axs_batteries(front=False)[0], "when": {"shifting": ["AXS"]}},
        {"key": "crankset", "type": "CRANKSET", "name": "crankset", "model": "Apex 1 Wide crankset {crank_length} mm",
         "specs": {"speeds": "1×12", "crank length": "{crank_length} mm", "chainring": "{ring}T",
                   "spindle": "DUB (28.99 mm)"},
         "mount": {"slot": "CRANKSET"}},
        chainring_1x("Apex X-Sync chainring {ring}T"),
        bottom_bracket("DUB (28.99 mm)"),
        {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
         "specs": {"speeds": "12", "range": "{cassette}T", "sprockets": "{sprockets}",
                   "freehub": "Standard 11-speed (HG) freehub"},
         "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
        *chain("Apex Flattop chain", {"speeds": "12 (Flattop)", "joining": "Flattop PowerLock"},
               "SRAM Flattop PowerLock", {"speeds": "12", "reuse": "SRAM: single use, fit a new one after opening"}),
        *brakes("Apex HRD caliper", {"caliper": "Flat mount, 2 pistons", "fluid": "DOT 5.1", "rotor": "160 mm"}),
        *pads("SRAM road disc brake pads (organic)", {"compound": "Organic", "fits": "Apex HRD calipers"}),
        *rotors("SRAM CenterLine {size} mm", {"mount": "6-bolt or Center Lock (check your hubs)"}),
        *[{**c, "when": {"shifting": ["MECH"]}}
          for c in shift_cables("SRAM shift cable", "SRAM shift housing") if c["key"].endswith("rear")],
    ])
