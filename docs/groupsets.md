# Groupset import

Adds every component of a groupset in one action instead of entering each part by hand.

## Use it
Bike page → **Add groupset**. Choose the options (crank length, chainrings, crankset with or without power
meter, cassette, rotor sizes, bottom bracket), untick parts you don't want, and choose what happens when a
position already has a part:

- **Keep the current part** (default): the new part is added as a spare.
- **Replace**: the old part is removed and gets its usual outcome (pads → discarded, others → stored spare).
  Its mileage and history are kept.

The list shows, per part, exactly what will happen before anything is saved. Cassette and rotors go on the
wheels that are installed on the bike; without a wheel they are added as spares. Chainrings go on the new
crankset and the quick link on the new chain. With "No bike" everything is added as spares.

**How was it bought?** Choose **As one bundle** (default) to enter one price, shop and date for the whole
set: the price counts once in the bike's running cost and the parts get no own price (each part shows an
estimated share). Choose **Part by part** to enter a price per part instead. Tick **spare** on a part to
put it into storage instead of onto the bike (for example a BSA bottom bracket that does not fit); it
stays part of the bundle. Parts replaced later (pads, rotor, chain) are bought separately and get their own
price; the originals stay listed in the bundle as retired or stored. Already imported without a bundle?
Bike page → **Bought as a bundle** → **Group parts as a bundle**, tick the parts, enter the price.

The whole import is one work session: Inventory → History → **Undo** takes it all back (the records stay,
marked as an undone operation, and the bundle is voided). Products are reused: importing the same group on a second bike creates no
duplicate products.

## Shimano Ultegra Di2 R8100 (2×12, hydraulic disc)

| Part | Model | Goes to |
|---|---|---|
| Di2 levers | ST-R8170 (wireless, CR1632 coin cell per lever) | bike · shifters |
| Front derailleur | FD-R8150 (braze-on, max 52T, capacity 16T) | bike |
| Rear derailleur | RD-R8150 (max 34T, capacity 39T, charging port) | bike |
| Crankset | FC-R8100 or FC-R8100-P, 160/165/170/172.5/175 mm, Hollowtech II 24 mm | bike |
| Chainrings | 50/34 or 52/36 | crankset |
| Bottom bracket | SM-BB-R60 (BSA 68) or SM-BB72-41B (press-fit), or none | bike |
| Cassette | CS-R8100-12, 11-30 or 11-34 (fits HG 11-speed road freehub) | rear wheel |
| Chain | CN-M8100, 12-speed, 116 links | bike |
| Quick link | SM-CN910-12 | chain |
| Brakes front/rear | BR-R8170 flat mount, SM-BH90-JK-SSR hose, Shimano mineral oil | bike |
| Pads front/rear | L05A-RF resin with fins | bike |
| Rotors | RT-CL800 Center Lock, 160 or 140 mm each | wheels |
| Battery | BT-DN300 internal | bike |
| Di2 wires (unticked by default) | EW-SD300 | bike |

**Source and status:** gathered 2026-10-25 from retailer listings of the full groupset and its parts.
shimano.com was not reachable from the build environment, so the template is marked **unverified** and
the app says so. Check the specs against productinfo.shimano.com (ULTEGRA R8100 series) and correct the
template where needed; the products created from it carry the source in their notes.

## Add another groupset
1. Copy `backend/bikelog/groupset_templates/shimano_ultegra_di2_r8100.py` to a new module.
2. Change `code`, `name`, `options` and `items` (format is described in
   `backend/bikelog/groupset_templates/__init__.py`).
3. Register it in `TEMPLATES` in that `__init__.py`.
4. Run `pytest backend/tests/test_groupsets.py`: `test_shipped_templates_are_consistent` checks every
   option combination against the part types, positions and parents.
No other code or UI change is needed.
