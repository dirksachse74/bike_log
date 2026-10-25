"""Shimano GRX 12-speed (gravel): Di2 RX825 2×12 and mechanical RX820 1×12, hydraulic disc brakes (BR-RX820).

Model numbers from retailer listings and launch news found on 2026-10-26 (bike-components.de, bike24.com,
eatsleepcycle.com, veloplus.ee, road.cc). Several retailer listings disagree (for example on 1× Di2 rear
derailleurs), and shimano.com was not reachable from the build environment, so both templates are marked
unverified until checked against https://productinfo.shimano.com (GRX RX820 series).
"""
from bikelog.groupset_templates._shared import (
    bb_option, bottom_bracket, brakes, cassette_option, chain, chainring_1x, chainrings_2x, crank_length_option,
    gearing_option, pads, pulleys, ring_option, rotor_options, rotors, shift_cables,
)

SOURCE = ("Retailer listings and launch news of GRX RX820/RX825 (bike-components.de, bike24.com, eatsleepcycle.com, "
          "veloplus.ee, road.cc), 2026-10-26; not yet checked against productinfo.shimano.com")
BB = bb_option([("BSA", "Threaded BSA 68 mm (SM-BB-R60)", "SM-BB-R60", "BSA threaded, 68 mm shell"),
                ("PF", "Press-fit BB86 / BB92 (SM-BB72-41B)", "SM-BB72-41B", "Press-fit BB86 / BB92 (41 mm)")], "BSA")


def _brakes(lever: str) -> list[dict]:
    return [
        *brakes("BR-RX820", {"caliper": "BR-RX820, flat mount, 2 pistons", "lever": lever,
                             "fluid": "Shimano mineral oil", "rotor": "140 / 160 mm"}),
        *pads("L05A-RF", {"compound": "Resin", "cooling": "Fins", "fits": "BR-RX820 (check the caliper manual)"}),
        *rotors("RT-MT800 {size} mm", {"mount": "Center Lock", "technology": "Ice Tech Freeza"}),
    ]


CHAIN = chain("CN-M8100", {"speeds": "12 (Hyperglide+)", "links": "126 (shorten to fit)",
                           "joining": "Quick link SM-CN910-12"},
              "SM-CN910-12", {"speeds": "12", "reuse": "Shimano recommends a new link after opening"})

TEMPLATE_DI2 = {
    "code": "SHIMANO_GRX_DI2_RX825_2X12",
    "name": "Shimano GRX Di2 RX825 · 2×12 · hydraulic disc",
    "maker": "Shimano",
    "series": "GRX RX825 Di2",
    "label_prefix": "GRX",
    "speeds": 12,
    "source": SOURCE,
    "checked_on": "2026-10-26",
    "verified": False,
    "notes": "Semi-wireless Di2: wireless levers on coin cells, derailleurs wired to the internal BT-DN300 battery.",
    "options": [
        crank_length_option(("165", "170", "172.5", "175"), "172.5"),
        gearing_option([("48", "31", "")], "48-31"),
        cassette_option({"11-34": "11-12-13-14-15-17-19-21-24-27-30-34",
                         "11-36": "11-12-13-14-15-17-19-21-24-28-32-36"}, "11-36", "CS-HG710-12 {cassette}"),
        *rotor_options(front="160", rear="160"),
        BB,
    ],
    "items": [
        {"key": "shifters", "type": "SHIFTERS", "name": "Di2 levers", "model": "ST-RX825",
         "specs": {"function": "Dual control levers, 2×12 Di2, hydraulic disc brake",
                   "connection": "Wireless to the derailleurs", "power": "Coin cell in each lever",
                   "brake fluid": "Shimano mineral oil"},
         "mount": {"slot": "SHIFTERS"}},
        {"key": "front_derailleur", "type": "FRONT_DERAILLEUR", "name": "front derailleur", "model": "FD-RX825",
         "specs": {"speeds": "2×12", "mount": "Braze-on", "wire": "EW-SD300"}, "mount": {"slot": "FRONT_DERAILLEUR"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": "RD-RX825",
         "specs": {"speeds": "12", "max low sprocket": "36T", "clutch": "Shadow RD+",
                   "charging": "Charging port for EW-EC300"},
         "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys("RD-RX825", "13"),
        {"key": "crankset", "type": "CRANKSET", "name": "crankset", "model": "FC-RX820-2 {crank_length} mm",
         "specs": {"speeds": "2×12", "crank length": "{crank_length} mm", "chainrings": "{outer}-{inner}T",
                   "spindle": "Hollowtech II, 24 mm"},
         "mount": {"slot": "CRANKSET"}},
        *chainrings_2x("FC-RX820-2 chainring {teeth}T"),
        bottom_bracket("24 mm (Hollowtech II)"),
        {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
         "specs": {"speeds": "12", "range": "{cassette}T", "sprockets": "{sprockets}",
                   "freehub": "Shimano HG road freehub"},
         "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
        *CHAIN,
        *_brakes("ST-RX825"),
        {"key": "battery", "type": "BATTERY", "name": "Di2 battery", "model": "BT-DN300",
         "specs": {"system": "Shimano Di2", "mount": "internal (seatpost or frame)",
                   "charging": "EW-EC300 cable at the rear derailleur port"},
         "mount": {"slot": "BATTERY"}},
        {"key": "wires", "type": "OTHER", "name": "Di2 wires", "model": "EW-SD300 wire set",
         "specs": {"connects": "Battery to front and rear derailleur",
                   "lengths": "Depend on the frame; measure before ordering"},
         "mount": {"slot": "DI2_WIRES"}, "default": False},
    ],
}

TEMPLATE_MECHANICAL_1X = {
    "code": "SHIMANO_GRX_RX820_1X12",
    "name": "Shimano GRX RX820 mechanical · 1×12 · hydraulic disc",
    "maker": "Shimano",
    "series": "GRX RX820",
    "label_prefix": "GRX",
    "speeds": 12,
    "source": SOURCE,
    "checked_on": "2026-10-26",
    "verified": False,
    "notes": "Cable shifting, one chainring. The 10-45 / 10-51 cassettes need a Shimano Micro Spline freehub. "
             "Set the bike's shifting to Mechanical so the cable reminders apply.",
    "options": [
        crank_length_option(("165", "170", "172.5", "175"), "172.5"),
        ring_option(["38", "40", "42"], "40"),
        cassette_option({"10-45": "10-12-14-16-18-21-24-28-32-36-40-45",
                         "10-51": "10-12-14-16-18-21-24-28-33-39-45-51"}, "10-45", "CS-M8100-12 {cassette}"),
        *rotor_options(front="160", rear="160"),
        BB,
    ],
    "items": [
        {"key": "shifters", "type": "SHIFTERS", "name": "levers", "model": "ST-RX820",
         "specs": {"function": "Shift/brake lever right (1×12 mechanical) + brake lever left, hydraulic disc",
                   "brake fluid": "Shimano mineral oil"},
         "mount": {"slot": "SHIFTERS"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": "RD-RX822-SGS",
         "specs": {"speeds": "12", "max low sprocket": "51T", "clutch": "Shadow RD+"},
         "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys("RD-RX822", "13"),
        {"key": "crankset", "type": "CRANKSET", "name": "crankset", "model": "FC-RX820-1 {crank_length} mm",
         "specs": {"speeds": "1×12", "crank length": "{crank_length} mm", "chainring": "{ring}T",
                   "spindle": "Hollowtech II, 24 mm"},
         "mount": {"slot": "CRANKSET"}},
        chainring_1x("SM-CRX820-1 {ring}T"),
        bottom_bracket("24 mm (Hollowtech II)"),
        {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
         "specs": {"speeds": "12", "range": "{cassette}T", "sprockets": "{sprockets}",
                   "freehub": "Shimano Micro Spline"},
         "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
        *CHAIN,
        *_brakes("ST-RX820"),
        *[c for c in shift_cables("Shimano shift cable", "Shimano shift housing") if c["key"].endswith("rear")],
    ],
}
