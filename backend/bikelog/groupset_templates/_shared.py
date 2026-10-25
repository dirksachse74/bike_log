"""Building blocks shared by several groupset templates (options and items that only differ in model names).

Each function returns plain template data (dicts), the same shape a template module would write out by hand.
"""
from __future__ import annotations


def crank_length_option(lengths=("160", "165", "170", "172.5", "175"), default="172.5") -> dict:
    return {"key": "crank_length", "label": "Crank length", "default": default,
            "choices": [{"value": v, "label": f"{v} mm", "vars": {"crank_length": v}} for v in lengths]}


def gearing_option(pairs: list[tuple[str, str, str]], default: str) -> dict:
    """2× chainrings: (outer, inner, label suffix) per choice."""
    assert default in {f"{o}-{i}" for o, i, _ in pairs}, default
    return {"key": "gearing", "label": "Chainrings", "default": default,
            "choices": [{"value": f"{o}-{i}", "label": f"{o}-{i}{' (' + s + ')' if s else ''}",
                         "vars": {"outer": o, "inner": i}} for o, i, s in pairs]}


def ring_option(sizes: list[str], default: str) -> dict:
    """1× chainring size."""
    return {"key": "ring", "label": "Chainring", "default": default,
            "choices": [{"value": t, "label": f"{t}T", "vars": {"ring": t}} for t in sizes]}


def cassette_option(ranges: dict[str, str], default: str, model: str) -> dict:
    """ranges: "11-34" -> sprocket list. ``model`` may use {cassette}."""
    return {"key": "cassette", "label": "Cassette", "default": default,
            "choices": [{"value": r, "label": r,
                         "vars": {"cassette": r, "sprockets": s, "cassette_model": model.format(cassette=r)}}
                        for r, s in ranges.items()]}


def rotor_options(sizes=("160", "140"), front="160", rear="140") -> list[dict]:
    return [{"key": "rotor_front", "label": "Front rotor", "default": front,
             "choices": [{"value": v, "label": f"{v} mm", "vars": {"rotor_front": v}} for v in sizes]},
            {"key": "rotor_rear", "label": "Rear rotor", "default": rear,
             "choices": [{"value": v, "label": f"{v} mm", "vars": {"rotor_rear": v}} for v in sizes]}]


def bb_option(choices: list[tuple[str, str, str, str]], default: str) -> dict:
    """(value, label, model, standard); a "NONE" choice (keep my bottom bracket) is added."""
    return {"key": "bottom_bracket", "label": "Bottom bracket", "default": default,
            "choices": [{"value": v, "label": lbl, "vars": {"bb_model": m, "bb_standard": std}}
                        for v, lbl, m, std in choices]
            + [{"value": "NONE", "label": "Other / keep my bottom bracket", "vars": {}}]}


def bottom_bracket(spindle: str) -> dict:
    return {"key": "bottom_bracket", "type": "BOTTOM_BRACKET", "name": "bottom bracket", "model": "{bb_model}",
            "specs": {"standard": "{bb_standard}", "spindle": spindle},
            "mount": {"slot": "BOTTOM_BRACKET"}, "when": {"bottom_bracket": ["BSA", "PF"]}}


def pulleys(rd_model: str, teeth: str, speeds: str = "12") -> list[dict]:
    return [{"key": "pulley_upper", "type": "PULLEY_WHEEL", "name": "upper pulley (guide)",
             "model": f"{rd_model} guide pulley", "specs": {"speeds": speeds, "teeth": teeth},
             "mount": {"parent": "rear_derailleur", "slot": "PULLEY_UPPER"}},
            {"key": "pulley_lower", "type": "PULLEY_WHEEL", "name": "lower pulley (tension)",
             "model": f"{rd_model} tension pulley", "specs": {"speeds": speeds, "teeth": teeth},
             "mount": {"parent": "rear_derailleur", "slot": "PULLEY_LOWER"}}]


def chainrings_2x(model: str) -> list[dict]:
    """``model`` may use {outer}/{inner}/{teeth}."""
    return [{"key": "chainring_outer", "type": "CHAINRING", "name": "outer chainring {outer}T",
             "model": model.replace("{teeth}", "{outer}"),
             "specs": {"teeth": "{outer}", "position": "outer", "for": "{outer}-{inner}T"},
             "mount": {"parent": "crankset", "slot": "CHAINRING_OUTER"}},
            {"key": "chainring_inner", "type": "CHAINRING", "name": "inner chainring {inner}T",
             "model": model.replace("{teeth}", "{inner}"),
             "specs": {"teeth": "{inner}", "position": "inner", "for": "{outer}-{inner}T"},
             "mount": {"parent": "crankset", "slot": "CHAINRING_INNER"}}]


def chainring_1x(model: str) -> dict:
    return {"key": "chainring", "type": "CHAINRING", "name": "chainring {ring}T", "model": model,
            "specs": {"teeth": "{ring}", "position": "single (1×)"},
            "mount": {"parent": "crankset", "slot": "CHAINRING_OUTER"}}


def chain(model: str, specs: dict, link_model: str, link_specs: dict) -> list[dict]:
    return [{"key": "chain", "type": "CHAIN", "name": "chain", "model": model, "specs": specs,
             "mount": {"slot": "CHAIN"}},
            {"key": "quick_link", "type": "QUICK_LINK", "name": "quick link", "model": link_model,
             "specs": link_specs, "mount": {"parent": "chain", "slot": "QUICK_LINK"}}]


def brakes(caliper: str, specs: dict) -> list[dict]:
    return [{"key": f"brake_{end}", "type": "BRAKE_CIRCUIT", "name": f"{end} brake", "model": f"{caliper} {end}",
             "specs": specs, "mount": {"slot": f"{end.upper()}_BRAKE"}} for end in ("front", "rear")]


def pads(model: str, specs: dict) -> list[dict]:
    return [{"key": f"pads_{end}", "type": "BRAKE_PADS", "name": f"{end} pads", "model": model, "specs": specs,
             "mount": {"slot": f"{end.upper()}_PADS"}} for end in ("front", "rear")]


def rotors(model: str, specs: dict) -> list[dict]:
    """``model`` may use {size}."""
    out = []
    for end, wheel in (("front", "FRONT_WHEEL"), ("rear", "REAR_WHEEL")):
        size = "{rotor_" + end + "}"
        out.append({"key": f"rotor_{end}", "type": "BRAKE_ROTOR", "name": f"{end} rotor {size} mm",
                    "model": model.replace("{size}", size), "specs": {"size": f"{size} mm", **specs},
                    "mount": {"wheel": wheel, "slot": "ROTOR"}})
    return out


def shift_cables(model: str, housing: str) -> list[dict]:
    """Mechanical shifting: inner cables and housing, front and rear (front only when there is a front derailleur)."""
    out = []
    for end in ("rear", "front"):
        out.append({"key": f"cable_{end}", "type": "SHIFT_CABLE", "name": f"{end} shift cable", "model": model,
                    "specs": {"position": end}, "mount": {"slot": f"SHIFT_CABLE_{end.upper()}"}})
        out.append({"key": f"housing_{end}", "type": "SHIFT_HOUSING", "name": f"{end} shift housing",
                    "model": housing, "specs": {"position": end}, "mount": {"slot": f"SHIFT_HOUSING_{end.upper()}"}})
    return out


# SRAM AXS: each derailleur carries its own battery (the same battery fits front and rear). SRAM gives about
# 60 hours of riding per charge for the RED AXS road derailleurs (support.sram.com, "How long do the RED AXS
# front and rear derailleur batteries last"), so the charge reminder counts ride hours instead of km.
AXS_BATTERY_RULE = {"DI2_BATTERY_CHARGE": {
    "name": "Charge AXS battery", "interval_km": None, "warn_km": None, "interval_hours": 55, "warn_hours": 10,
    "notes": "SRAM: about 60 h of riding per charge for AXS road derailleurs (support.sram.com); 55 h leaves a "
             "margin. Not verified for this exact derailleur."}}


def axs_batteries(front: bool = True) -> list[dict]:
    ends = (("rear", "rear_derailleur"), ("front", "front_derailleur")) if front else (("rear", "rear_derailleur"),)
    return [{"key": f"battery_{end}", "type": "BATTERY", "name": f"AXS battery ({end} derailleur)",
             "model": "SRAM AXS battery", "specs": {"system": "SRAM AXS", "mount": f"on the {end} derailleur",
                                                    "charging": "SRAM AXS charger (USB)"},
             "mount": {"parent": parent, "slot": "BATTERY"}, "rules": AXS_BATTERY_RULE}
            for end, parent in ends]
