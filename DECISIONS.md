# Decisions and assumptions

Reversible decisions made without asking, so work could continue. Each says what to change if
you disagree. Dates are 2026-10-24 unless noted.

## Stack and runtime
1. **Stack as agreed**: Python 3.13, FastAPI, Pydantic, SQLAlchemy 2.1, SQLite, Alembic; React 19 +
   TypeScript + Vite served by the backend. All mileage, reminder and stock logic lives in Python
   services; the UI only displays it.
2. **One launcher, local only**: `python -m bikelog` (or `BikeLog.exe`) binds to 127.0.0.1, default port
   8765 (falls back to a free port), opens the browser. Mutations need a per-launch token
   (`X-BikeLog-Token`) and the Host header is checked (DNS rebinding). No CORS.
3. **Data outside the install folder**: `%LOCALAPPDATA%\BikeLog` on Windows, `~/.local/share/bikelog`
   elsewhere, or `BIKELOG_DATA_DIR`. A data folder inside the install folder is refused.
4. **Backups**: a backup before every schema upgrade, a daily backup on start (kept: last 10), manual
   backup/export/restore. Restore takes a safety backup first.
5. **Demo data only in demo mode**: `--demo` uses a separate `demo/` database. Seeding refuses a
   database that already has data.

## Time and mileage
6. **Times**: stored as UTC; date-only entries mean the start of the local day (Europe/Berlin by
   default, changeable in Settings; changing it recomputes ordering and all usage).
7. **Installation periods are start-inclusive, end-exclusive.** A ride on the day of a date-only part
   change goes to the part installed that day and is flagged "ambiguous change date" until you confirm
   the equipment on the ride. Add a clock time to avoid the flag.
8. **Usage is never accumulated**: `usage_contribution` is rebuilt per ride from rides, installations,
   explicit ride equipment and usage profiles, so repeating an operation cannot double-count.
9. **Starting mileage** has an effective date and an estimate flag; rides before that date are treated
   as already inside it. Unknown prior use shows totals as "≥" (a minimum); estimates as "≈".
10. **Direct-drive trainer profile** removes wheels (and what is mounted on them: tires, tubes,
    cassette, rotors) and brake pads from VirtualRide/trainer rides. Editable per profile.
11. **Explicit ride equipment** works per bike-level slot (e.g. which chain or wheel was used); parts
    mounted on that part follow it.

## Maintenance
12. Rules list the actions that reset them. Liquid wax never postpones hot wax; a bleed never resets
    the 2-year fluid interval; snoozing records no maintenance. A logged reset/cycle action clears
    obsolete snoozes.
13. A maintenance entry dated the same day as a ride counts as done *before* that ride when both are
    date-only (open question: say if you prefer "after").

## Spare parts and replacement (Dirk's specs of 22:45, 22:47 and 22:49)
14. **Three tracking modes**: individual items are components (own identity and history); counted
    stock and bulk supplies are stock lines (`consumable` table, `tracking_mode` COUNTED or BULK).
    The table keeps its old name to avoid a risky rebuild of existing data.
15. **Never both stock and installed**: identical unused parts are a quantity per product. Installing
    one (from Replace or "Install one") creates its individual component *in the same transaction* as
    the stock decrease. Individually tracked spares of the same product are shown next to the count.
16. **Removed-item outcomes**: Stored spare, Awaiting inspection/repair, Retired, Discarded, Sold/given
    away. Out-of-use outcomes keep the component and all history (the database refuses deletes). Default
    suggestions per type: bar tape, pads, quick links → Discarded; tubes → Awaiting repair; others → Stored.
17. **A part awaiting repair cannot be installed** until a repair is logged (a successful outcome such as
    "Repaired" returns it to the spares automatically) or its status is changed.
18. **Work sessions**: each user action (replace, move, install, remove, log maintenance, stock change)
    is one work session that groups its separate transactions. Undo works per session and is refused
    when later records depend on it. Parts created by an undone session stay as "record of an undone
    operation" so nothing disappears.
19. **Costs count once**: only purchases (and returns) carry money; using stock never does. A part
    bought during a replacement carries its price; a part drawn from stock has no own price.
20. **Stock units**: one unit is one usable item (a tube, one pad set for one caliper, one rotor, one
    chain, one quick link, one bar tape package). Packages are recorded separately on the purchase.
21. **Compatibility** is stored per product and bike, verified or not. Spares are labelled "verified
    fit", "listed, not verified", "same product" or "not recorded".
22. **Shopping list** is suggestions only, from optional minimum stock. Nothing is ordered.
23. **Inner tubes and quick links** were added as component types (tube on a wheel, quick link on a chain).

## Imports and Strava
24. Source identity `(source kind, account, reference)` is unique in the database. The Strava export
    CSV and the API use the same identity.
25. Imports never change inclusion: excluded rides stay excluded. Local edits are stored as overrides
    and survive re-imports.
26. **Strava API connector is isolated and off by default** (`BIKELOG_ENABLE_STRAVA=1`). Your earlier
    choice (permanent storage at your own risk) is supported, but no live connection was ever made; see
    docs/strava.md for the exact blockers.

## Groupsets (Dirk's request of 2026-10-25)
28. **Groupset templates are data** (`bikelog/groupset_templates/`), one module per groupset, checked by a
    test for every option combination. Importing creates products (reused by maker + model) and one
    component per part in a single work session, so it can be undone in one step.
29. **Occupied positions are kept by default**: the new part becomes a spare unless you choose Replace.
    Wheel-mounted parts (cassette, rotors) go on the installed wheels, or become spares without wheels.
30. **Ultegra Di2 R8100 data is unverified**: taken from retailer listings because shimano.com was not
    reachable here. The app shows a warning; correct the template after checking Shimano's spec pages.
    Di2 wires are offered but unticked (lengths depend on the frame); the charging cable is a tool, not a part.

## Costs and journal (Dirk's requests of 2026-10-25)
31. **Initial cost** is the bike's purchase price (with date). **Running cost is never typed in or
    stored**: it is added up each time from part prices, stock used and service costs, so corrections and
    undo change it automatically.
32. **Each euro is counted once**: a part's price counts for the bike it was *first* installed on (moving
    it later does not move the cost; parts on a wheel/crankset follow that part's bike). Spares never
    installed count for no bike. A part drawn from stock has no own price; its share is the stock line's
    average purchase price, marked ≈. A product's reference price is information only, never spent money.
33. Parts that came with the bike: leave their price empty (they are inside the purchase price). The
    bike page lists how many installed parts have no price.
34. A cost on a maintenance entry logged for several parts is one fee, stored on the first entry only.
35. **Journal**: dated notes (Note or Issue, issues can be marked resolved) on a bike or a part. A part's
    entries also record its bike, so they show in the bike journal. Notes written on maintenance entries
    (symptom, work done, notes) appear in the same journal, read-only, so there is one place to read what
    happened. Entries can be edited or removed (voided, never deleted).

## Repository
27. Pushed only to the feature branch `claude/project-thread-6y3mmh` of the private repository. Demo
    data uses fictional Strava gear ids.
