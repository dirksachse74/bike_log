"""Groupset templates: every component of a groupset, so a whole group can be added in one action.

Each template is plain data (one module per groupset, registered in TEMPLATES below). To add a groupset,
copy an existing module, change the items and options, and add it to TEMPLATES; no other code changes.

Template fields
- code, name, maker, series, speeds, notes
- source / checked_on / verified: where the data comes from and whether it was checked against the
  maker's own documentation (shown in the app; unverified data is marked as such)
- options: choices made at import time (crank length, gearing, cassette, rotor sizes, bottom bracket).
  Each choice has ``vars`` that are filled into the ``{placeholders}`` of item models and specs.
- items: one entry per physical component
  - key: unique within the template (other items refer to it as a parent)
  - type: a component type code from bikelog.catalog
  - name: short name used in the label ("<prefix> <name>")
  - model: the product model; together with the maker it identifies the product
  - specs: dict of product specs (strings may use {placeholders})
  - mount: where it goes when installed on a bike, one of
      {"slot": S}                      on the bike in slot S
      {"wheel": W, "slot": S}          on the wheel installed in the bike's slot W (FRONT_WHEEL/REAR_WHEEL)
      {"parent": key, "slot": S}       on another item of this template (e.g. chainring on the crankset)
  - default: included unless the user leaves it out (False: offered, unticked)
  - when: optional {option_key: [values]}; the item is only offered for those choices
  - rules: optional {rule_code: {field: value}}: the part gets its own version of that default rule
    (e.g. SRAM AXS batteries: charge every 55 ride hours instead of the Di2 battery's 800 km)
Shared building blocks (brakes, rotors, chain + quick link, AXS batteries, options) are in _shared.py.
"""
from __future__ import annotations

from bikelog.groupset_templates import (
    shimano_105_r7100, shimano_dura_ace_di2_r9200, shimano_grx_rx820, shimano_ultegra_di2_r8100, sram_road_axs,
)

TEMPLATES: dict[str, dict] = {t["code"]: t for t in [
    shimano_ultegra_di2_r8100.TEMPLATE,      # first = preselected in the app
    shimano_dura_ace_di2_r9200.TEMPLATE,
    shimano_105_r7100.TEMPLATE_DI2,
    shimano_105_r7100.TEMPLATE_MECHANICAL,
    shimano_grx_rx820.TEMPLATE_DI2,
    shimano_grx_rx820.TEMPLATE_MECHANICAL_1X,
    sram_road_axs.RED_E1,
    sram_road_axs.FORCE,
    sram_road_axs.RIVAL,
    sram_road_axs.APEX_XPLR,
    sram_road_axs.RED_XPLR_13,
    sram_road_axs.FORCE_XPLR_13,
]}
