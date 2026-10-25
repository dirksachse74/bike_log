"""Shimano 105 R7100 series, 2×12 speed, hydraulic disc brakes: Di2 (R7150, ST-R7170 levers) and mechanical
(R7100, ST-R7120 levers). Both share crankset, cassette, chain, calipers and rotors.

Model numbers from retailer listings and reviews found on 2026-10-26 (bike24.com, bike-components.de,
mariposabicycles.ca, road.cc, bikeradar.com, tunecycles.com.au, Shimano's own launch news for the mechanical
group). shimano.com product pages were not reachable from the build environment, so both templates are
marked unverified until checked against https://productinfo.shimano.com (105 R7100 series).
"""
from bikelog.groupset_templates._shared import (
    bb_option, bottom_bracket, brakes, cassette_option, chain, chainrings_2x, crank_length_option, gearing_option,
    pads, pulleys, rotor_options, rotors, shift_cables,
)

SOURCE = ("Retailer listings and reviews of the 105 R7100/R7150 groupsets (bike24.com, bike-components.de, road.cc, "
          "bikeradar.com, tunecycles.com.au), 2026-10-26; not yet checked against productinfo.shimano.com")


def _options() -> list[dict]:
    return [
        crank_length_option(),
        gearing_option([("50", "34", "compact"), ("52", "36", "mid-compact")], "50-34"),
        cassette_option({"11-34": "11-12-13-14-15-17-19-21-24-27-30-34",
                         "11-36": "11-12-13-14-15-17-19-21-24-28-32-36"}, "11-34", "CS-R7101-12 {cassette}"),
        *rotor_options(),
        bb_option([("BSA", "Threaded BSA 68 mm (SM-BB-R60)", "SM-BB-R60", "BSA threaded, 68 mm shell"),
                   ("PF", "Press-fit BB86 / BB92 (SM-BB72-41B)", "SM-BB72-41B", "Press-fit BB86 / BB92 (41 mm)")],
                  "BSA"),
    ]


def _common(lever: str) -> list[dict]:
    return [
        {"key": "crankset", "type": "CRANKSET", "name": "crankset", "model": "FC-R7100 {crank_length} mm",
         "specs": {"speeds": "2×12", "crank length": "{crank_length} mm", "chainrings": "{outer}-{inner}T",
                   "spindle": "Hollowtech II, 24 mm"},
         "mount": {"slot": "CRANKSET"}},
        *chainrings_2x("FC-R7100 chainring {teeth}T"),
        bottom_bracket("24 mm (Hollowtech II)"),
        {"key": "cassette", "type": "CASSETTE", "name": "cassette {cassette}", "model": "{cassette_model}",
         "specs": {"speeds": "12", "range": "{cassette}T", "sprockets": "{sprockets}",
                   "freehub": "Shimano HG road freehub (11-36 is also sold as CS-HG710-12)"},
         "mount": {"wheel": "REAR_WHEEL", "slot": "CASSETTE"}},
        *chain("CN-M7100", {"speeds": "12 (Hyperglide+)", "links": "116 or 126 (shorten to fit)",
                            "joining": "Quick link SM-CN910-12"},
               "SM-CN910-12", {"speeds": "12", "reuse": "Shimano recommends a new link after opening"}),
        *brakes("BR-R7170", {"caliper": "BR-R7170, flat mount, 2 pistons", "lever": lever,
                             "fluid": "Shimano mineral oil", "rotor": "140 / 160 mm"}),
        *pads("L05A-RF", {"compound": "Resin", "cooling": "Fins", "fits": "BR-R7170 (check the caliper manual)"}),
        *rotors("RT-CL800 {size} mm", {"mount": "Center Lock",
                                       "alternative": "105 kits also ship with SM-RT70 rotors"}),
    ]


TEMPLATE_DI2 = {
    "code": "SHIMANO_105_DI2_R7150",
    "name": "Shimano 105 Di2 R7150 · 2×12 · hydraulic disc",
    "maker": "Shimano",
    "series": "105 R7150 Di2",
    "label_prefix": "105",
    "speeds": 12,
    "source": SOURCE,
    "checked_on": "2026-10-26",
    "verified": False,
    "notes": "Semi-wireless Di2 like Ultegra R8100: wireless levers on coin cells, derailleurs wired to the "
             "internal BT-DN300 battery, charged at the rear derailleur.",
    "options": _options(),
    "items": [
        {"key": "shifters", "type": "SHIFTERS", "name": "Di2 levers", "model": "ST-R7170",
         "specs": {"function": "Dual control levers, 2×12 Di2, hydraulic disc brake",
                   "connection": "Wireless to the derailleurs", "power": "CR1632 coin cell in each lever",
                   "brake fluid": "Shimano mineral oil"},
         "mount": {"slot": "SHIFTERS"}},
        {"key": "front_derailleur", "type": "FRONT_DERAILLEUR", "name": "front derailleur", "model": "FD-R7150",
         "specs": {"speeds": "2×12", "mount": "Braze-on", "wire": "EW-SD300"}, "mount": {"slot": "FRONT_DERAILLEUR"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": "RD-R7150",
         "specs": {"speeds": "12", "max low sprocket": "36T", "charging": "Charging port for EW-EC300",
                   "wire": "EW-SD300"},
         "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys("RD-R7150", "13"),
        *_common("ST-R7170"),
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

TEMPLATE_MECHANICAL = {
    "code": "SHIMANO_105_R7100",
    "name": "Shimano 105 R7100 mechanical · 2×12 · hydraulic disc",
    "maker": "Shimano",
    "series": "105 R7100",
    "label_prefix": "105",
    "speeds": 12,
    "source": SOURCE,
    "checked_on": "2026-10-26",
    "verified": False,
    "notes": "Cable shifting with hydraulic disc brakes (Shimano: the mechanical 105 R7100 is hydraulic-only). "
             "Set the bike's shifting to Mechanical so the cable reminders apply.",
    "options": _options(),
    "items": [
        {"key": "shifters", "type": "SHIFTERS", "name": "levers", "model": "ST-R7120",
         "specs": {"function": "Dual control levers, 2×12 mechanical, hydraulic disc brake",
                   "brake fluid": "Shimano mineral oil"},
         "mount": {"slot": "SHIFTERS"}},
        {"key": "front_derailleur", "type": "FRONT_DERAILLEUR", "name": "front derailleur", "model": "FD-R7100",
         "specs": {"speeds": "2×12", "mount": "Braze-on (band clamp version also sold)"},
         "mount": {"slot": "FRONT_DERAILLEUR"}},
        {"key": "rear_derailleur", "type": "REAR_DERAILLEUR", "name": "rear derailleur", "model": "RD-R7100",
         "specs": {"speeds": "12", "max low sprocket": "36T", "design": "Shadow RD"},
         "mount": {"slot": "REAR_DERAILLEUR"}},
        *pulleys("RD-R7100", "13"),
        *_common("ST-R7120"),
        *shift_cables("Shimano road shift cable (OT-SP41 set)", "Shimano OT-SP41 shift housing"),
    ],
}
