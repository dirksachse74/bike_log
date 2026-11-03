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

## JSON product import (2026-10-25)
36. **One template per part type**, generated from `product_specs.py` (JSON Schema + example + agent
    instructions); a test keeps the shipped files in sync. Spec fields are optional; unknown spec keys are
    kept and reported, so a template never blocks useful data.
37. **Files are all-or-nothing** with every error listed by path. Products are matched by type + maker +
    model: re-import is a no-op, changed values update (file wins, app-only keys kept). Items are spares
    matched by label. Only euro prices; scraped data is unverified unless the file says `verified: true`.
38. The command-line import writes a backup first and needs the app closed, like the other commands.

## Strava in Settings (2026-10-25)
39. Strava is set up entirely from Settings: app details (secret write-only, stored only in `strava.env`),
    browser OAuth with the callback on this app (`http://localhost:<port>/api/strava/callback`, single-use
    `state`, 15 min), sync in a background thread after a backup. The command-line commands stay. Changing the Client ID
    drops the old tokens. **Changed 2026-10-25 (Dirk): disconnecting keeps every ride**; it only stops
    syncing and revokes access. Dirk does not want mass deletes.

## Rides area (Dirk's request of 2026-10-25)
40. **Removing a ride never deletes it.** "Remove ride" moves it to Rides → *Removed rides*: it counts no
    km, keeps its source identity, so Strava sync, Re-read and CSV import never bring it back, and it can
    be restored. There is no bulk delete.
41. **The bike of a ride is yours to decide.** Pick a bike (or "no bike") per ride in the list, or tick
    several rides and assign them together. The choice is stored as a ride override, so it survives
    sync and Re-read; the list shows "changed by you · strava: X" with Strava's value. Rides without a
    bike are listed under *No bike* and count for no part.
42. **Sync looks back 30 days** (was 3) so gear changed on Strava for recent rides is picked up. Older
    changes come in with *Re-read all since start date*. Your own bike choice always wins.

## Reminders, tire setup, change log, logs (Dirk's requests of 2026-10-25)
43. **Tube or tubeless lives on the wheel** (`component.tire_setup`: TUBE, TUBELESS, TUBULAR or not set).
    A wheelset moved to another bike keeps its setup; the tire and tube on the wheel follow it. Set it on
    the bike page (wheel row) or the wheel's page.
44. **Sealant reminder is time-based**: top up every 3 months (changeable per part or per type, warning
    14 days before); a top-up or renewal resets it. It runs only when the tire's wheel is tubeless
    (`service_rule.requires_setup`); otherwise it shows "Not for this setup" and stays out of the to-do
    list. Brake fluid (24 months) was already time-based and is now tested end to end.
45. **Change log is automatic and separate from the journal**: every created part/bike, every changed
    field (old → new), every install/remove/correction is written by a database-session hook, with time,
    who (you in the app, Strava sync, CSV import, JSON import, demo) and the operation. It cannot be edited
    or deleted (triggers). It starts with this version; older history is in the installation and
    maintenance lists. Product (catalogue) edits are not in it yet.
46. **Diagnostics**: refused actions, operations, imports, syncs and unexpected errors (with traceback)
    go to the rotating log; Settings → Diagnostics shows and downloads it, redacting secrets again on
    the way out.
47. **Headset and power meter** are part types (a power meter can sit on the bike or on the crankset).
    Headset service default: 5000 km or 12 months. Power meter actions: zero offset, battery, firmware;
    no default reminder (add a time-based one per part if wanted).

48. **Every build says which code it is**: the backend commit (git, or `build_commit.txt` written by
    the PyInstaller spec) and the screens' commit (`frontend/dist/build-info.json` from Vite) are shown
    in Settings and by `--version`. A mismatch shows a red bar; the spec refuses to bundle a stale
    `frontend/dist`; a second start warns when an older copy is still running. Reason: Dirk saw the old
    Strava panel after updating (2026-10-25).
49. **One build script and commit-named installers**: `packaging/build.ps1` does pull → packages →
    tests → screens → exe → installer and stops at the first failure; installers are named
    `BikeLog-<version>-<commit>-setup.exe` (superseded by 50: the name now carries the version).
50. **Semantic versioning with one source**: `bikelog.__version__` (MAJOR.MINOR.PATCH) is the only place
    the number is written; Vite, the PyInstaller spec (exe file properties, `build_version.txt`) and the
    installer read it. The tagged release commit (`vX.Y.Z`) shows the plain number; other builds append
    the commit (`0.2.0+abc1234`, semver build metadata). `scripts/release.py` bumps, dates CHANGELOG.md,
    commits and tags on the feature branch; tags may be pushed, main is never touched. 0.1.0 = the first
    Windows build (untagged); 0.2.0 = first tagged release.
51. **Purchase bundles**: a groupset bought as one bundle (one price, shop, date) is a `purchase_bundle`
    with member parts that carry no own price, so the money is counted once, for the bike most members
    were first installed on. Per-part shares are shown as estimates only. Later replacements (pads,
    rotor, chain) are separate parts with their own price; originals stay members. Wrong bundles are
    voided, never deleted; undoing the import voids its bundle. Existing parts can be grouped later
    (bike page → Group parts as a bundle). Reason: Dirk bought his Ultegra group as a bundle (2026-10-25).
52. **Bundle parts kept as spares at import**: per item, "spare" puts it in storage although a bike is
    chosen (e.g. the BSA bottom bracket that does not fit the TIME NXR). It stays a bundle member.
53. **Km from before** is the part's starting mileage (value, "as of" date, estimate flag). The part
    page offers it when none is set and defaults the date to the day the part was first installed, so
    rides from then on count on top (e.g. wheels with a few thousand km on a bike with 150 km).
54. **Fresh start without losing anything**: Settings → Fresh start needs the typed word RESET, writes a
    backup named `…-kept-before-reset.db` that is never pruned, then empties the database in place (drop
    all tables/views/triggers in one exclusive transaction, migrate again, default rules) so it works
    while the app runs and on Windows (no rename of an open file). Strava app details and login
    (`strava.env`) are kept by default, with a tick box to clear them too. Any backup can be restored
    from Settings; a restore first writes a `…-kept-before-restore.db` backup. (Dirk 2026-10-25.)
55. **Ride incidents are journal issues**: an incident is a journal ISSUE with `ride_id` and
    `incident_type` (FLAT/CRASH/DEFECT/OTHER), dated on the ride, on the affected part (or the ride's
    bike). No separate table, so incidents get resolve/void/no-delete for free and show in every journal.
    A part's journal includes entries of parts mounted below it on that date. (Dirk 2026-10-25.)
56. **Dry/wet is local ride data** (`ride.conditions`), an editable field outside SOURCE_FIELDS, so a
    Strava re-sync or CSV re-import never overwrites it.
57. **Assemblies are parent installations**: wheelset → wheels → tire/tube/hub/spokes/rim tape/sensor,
    hub → bearings, rear derailleur → pulleys, crankset → chainrings, chain → quick link. Km flow down the
    parent chain, each part keeps its own km and starting mileage (a new tire on a 2,000 km wheel starts
    at 0). A bike has either two wheels or a wheelset. The crank spindle is not a part: on Hollowtech II
    it is part of the drive-side crank.
58. **Carry-over at replace**: child parts can move to the new part in the same work session; the
    default is on unless the child's own limit (PARENT_COUNT) is reached.
59. **Quick links by number of chains** (PARENT_COUNT, default 2): Connex/KMC/Shimano say reusable a few
    times, no km figure; counting chains served is what can be tracked.
60. **Ride-hour rules**: interval_hours/warn_hours count moving time since the last action; rides with
    no time are listed, not guessed. Used for charging: Assioma PRO RS-1 spec ≥60 h (up to 160 h after
    firmware), default 50 h (80 h since decision 77); Magene sensor ~500 h per retailers, default 400 h or 12 months (months are
    Dirk's guess). Di2 BT-DN300 ~1000 km per retailers, default 800 km. All PERSONAL/unverified.
61. **Charge rules start as "insufficient information"** until the first Charged is logged, because the
    state of charge at install is unknown. Lever coin-cell rule exists but is off by default (Dirk's
    the rule only matters for wireless levers such as ST-R8170; switch it on per part).
62. **Bike-level rules** live in `service_rule` with component_type "BIKE" (default) or `bike_id` (per
    bike), and maintenance events with a bike and no part. Reason: torque check, frame inspection and
    Di2 system checks concern the whole bike, not one part (coverage review 2026-10-25). Without a logged
    check they show "not enough info" instead of guessing from the purchase date.
63. **Torque re-check is part of the bike's torque check**, not one reminder per part: parts with a
    torque spec fitted after the last torque check and ridden since make it due, listed by name. Reason:
    a groupset import would otherwise raise 20 reminders at once.
64. **Measurements set the outcome only when none is picked**; a typed outcome wins. Limits are per action
    (Shimano pads/rotors MANUFACTURER, chain 0.5 % shop guidance; 0.4 % warning personal) and only apply
    when the unit matches.
65. **Setup-dependent rules** (tubeless, mechanical shifting, electronic shifting) stay in the catalog for
    other users and are NOT_APPLICABLE (hidden) where the setup does not match. Dirk: Di2 only, discs only,
    never tubeless. Wheels without a setting use the default tire setup (TUBE); bikes without a shifting
    setting count as electronic once a battery is fitted.
66. **Shoes are rider gear, not mounted parts**: put "in use" with a date (disposition IN_USE, history
    kept), they and their cleats count every ride that has a bike while in use, whatever the bike. Two
    pairs in use at once both count; store one to stop it.
67. **Event-based checks** (crash → frame/hanger, worn chain → cassette/chainrings, wet ride → re-wax,
    bed-in after fitting) are computed from the history on read, like every other reminder, and clear
    when the matching check is logged after the event.
68. **Unknown CSV bike names are kept, not guessed**: the ride gets no bike, is marked uncertain with
    "csv: NAME (no bike with this name)", and the import summary lists the names. Adding a bike with that
    name and importing again assigns the rides and clears the note. No fuzzy matching.
69. **"At least" instead of a guess**: km since a service done before a "km from before" date are a lower
    bound, because the km between the service and that date are inside the starting value.
70. **Rides inside a bike's starting km are not counted as rides** in the bike's ride count (shown apart),
    so rides and km agree. A ride before the purchase date is flagged, never moved or dropped.
71. **Part names carry no bike name** unless the plain name is taken (parts move between bikes; the
    database keeps labels unique per type, including records of undone imports).
72. **Groupset templates stay data, with shared building blocks** (`_shared.py`) for repeated parts
    (brakes, rotors, chain + quick link, AXS batteries). SRAM parts are named by product name where
    retailers disagree on part numbers; nothing is marked verified without the maker's own documentation.
73. **SRAM AXS batteries are parts of the derailleurs** (BATTERY may mount on a derailleur) and the
    template gives them a per-part charge rule in ride hours (55 h; SRAM: about 60 h).
74. **Sample data only in a database the app has just created**: the launcher checks that the file did
    not exist before opening it, and `seed_sample` refuses a database with any bike, part or ride. The whole
    database is flagged (`sample_data` setting) and every record is logged with source SAMPLE; Fresh start
    drops everything, flag included. Built from code with a fixed random seed (same sample every time),
    dates relative to the first start. Command-line runs (backup, export, Strava, product import) never seed.
75. **The yearly full service is one bike-level reminder with a checklist**, not a bundle of the per-part
    rules: logging it records which jobs were done (in `work_done`) and resets only itself, because a job
    like a brake bleed has its own interval and its own record on the part.
76. **Tire pressure is a free-text note on the tire** (`component.pressure_note`), not a number with
    units or a reminder: riders write "4.8 bar", "70 psi" or "4.5 wet". It lives on the tire, so it moves
    with the tire.
77. **Assioma pedal charge every 80 ride hours** (Dirk, 2026-10-26; Favero quotes 60 h, up to about 160 h
    with newer firmware). Changed defaults are applied by migration only to rows still at the old default.
78. **An incident affecting several things is one incident, stored as one journal issue per affected
    thing** (shared `incident_group`), so every part keeps the incident in its own journal and history,
    while the ride shows and edits it as one. Counts on the ride count incidents, not entries.
79. **What an incident can affect is data** (`catalog.INCIDENT_OPTIONS`), resolved against the parts on the
    bike on the ride date. When no such part is recorded, the position or body area is offered by name and
    saved as text (`affected`), so a flat can be logged even before tires are entered.
80. **Removing an incident voids it** (reason "incident removed") and Restore brings it back; unticking
    a part while editing voids only that part's entry. Nothing is deleted.
81. **Bike page groups are a display choice, not data**: "Installed now" is grouped by part category in
    the screen only (groupset = drivetrain, brakes, controls and the shifting battery), so no grouping has
    to be kept in sync when parts move. Groups start folded; due reminders stay in sight.
82. **Lint upgrades keep the same rules**: with eslint-plugin-react-hooks 7 only `rules-of-hooks` and
    `exhaustive-deps` are on (as with v5), not the React Compiler rules. esbuild's postinstall (it checks
    the platform binary) is approved by `allowScripts` written by `npm install-scripts approve esbuild`.
83. **Swaps are shortcuts to Replace, not a new operation**: Manage parts → Swap chain / wheels / wheelset
    / tire opens the existing Replace dialog for the installed part of that type, so spares, stock, the
    old part's outcome and carried-over parts behave exactly as before. A spare that already has parts in
    a position (a stored wheelset with its wheels) keeps them: those children of the old part are not
    ticked to move, and replace() refuses to carry a part into a taken position.
84. **A flat names the tube and/or the tire per wheel**: FLAT options are front/rear tube and front/rear
    tire (catalog.INCIDENT_OPTIONS); choices carry `wheel` and `damage` so the form asks "tube only" or
    "tube and tire" per wheel. Wheels set (or defaulting) to tubeless or tubular offer no tube. Older
    incidents on "Front tire"/"Rear tire" by name keep their text and still edit.
85. **Spares to keep are per part type, not per product**: setting `spare_minimums` (JSON, default
    {"INNER_TUBE": 2, "TIRE": 1}; 0 removes a type) is checked against counted stock of that type plus
    stored individual spares, whatever the brand. Below it, the type goes on the shopping list with the
    per-line minimums. Suggestions only; nothing is ordered.
86. **Overview shows what to act on and folds the rest**: Upcoming tasks keeps OVERDUE/DUE/ATTENTION
    open and folds DUE_SOON, SNOOZED and INSUFFICIENT_INFO; chains, brakes and recent rides are one folded
    line each.
87. **Incident = what happened, repair = what you did** (Dirk 2026-10-26): repairs are stored per affected
    entry (journal_entry.repair REPLACED/REPAIRED, repair_text, repaired_on, repair_session_id; migration
    0012). Each fix is one work session holding the replace, stock use, install or TUBE_PATCH event;
    undoing that session (Undo fix, or Inventory → History) clears the repair and reopens the incident.
    The incident is solved, on the latest fix date, only when every affected entry has a repair.
88. **Tubes default to stock items**: replacing an untracked tube position uses one unit of a counted
    INNER_TUBE stock line (no new part). Tires taken from stock, stored spares and newly bought tires are
    installed on the wheel at that position when the wheel is recorded. Body areas and whole-bike
    incidents have no Fix; Solved stays for those.
89. **One "Where does it go?" list, built by the backend** (spares.mount_targets, GET /api/mount-targets):
    every bike position and every part of a parent type (on active bikes, and off any bike), with the
    path (wheelset › wheel) and the occupant. Types with parent types go only on a part, except wheels,
    batteries, power meters and sensors (catalog.ON_BIKE_TOO), which may also sit on the bike itself.
90. **Broken spokes count on the wheel, not as a service rule**: SPOKE_REPLACE events on a wheel since its
    last WHEEL_RELACE (or since the spoke set was fitted) are counted by maintenance.spoke_info; the
    "Re-lace" item is computed (like the hanger-after-crash item) with the threshold in the setting
    spoke_relace_after (default 3), so no service_rule table rebuild was needed. A "Broken spoke"
    incident is fixed on the wheel (repairs._fix_spoke), never by replacing the wheel.
91. **The groupset is a view, not a stored record** (services/assemblies.py): it is the parts in groupset
    positions on the bike now (categories Drivetrain, Brakes, Controls and BATTERY, the same grouping as
    "Installed now"), plus groupset-type parts mounted on a non-groupset part (cassette and rotors on the
    wheels). Parts are swapped one at a time (chains every few thousand km, pads, cassette), so a stored
    groupset would need its own install/remove history and could drift from what is really on the bike.
    As a view a new chain joins by being installed and the old one leaves by being removed, with nothing
    to keep in sync. The name comes from the purchase bundle (groupset import), otherwise the most common
    maker; the price stays on the bundle (DECISIONS 51). Its km are bike km since the earliest groupset
    part still on it was installed; each part keeps its own km. Wheelsets stay a real part (they carry
    wheels and move between bikes as one). Part trees come from `assemblies.tree` (open installations).
92. **Chain rotation keeps almost nothing of its own** (services/chains.py, migration 0013): only
    component.rotation_bike_id (set when a chain first goes on a bike, or by hand) and component.mark.
    "On / waxed, ready / dirty" comes from maintenance.chain_row (hot wax and wear events); the prompt
    comes from the hot-wax rule of the chain on the bike (DUE_SOON or worse: swap to the ready chain that
    rested longest, or wax when none is ready); the timeline from installations and WAX_HOT events. A swap
    is inv.replace (old chain stored, keeps its km) in its own work session, so Undo works as everywhere.
    The hot-wax task of a rotation chain carries the prompt (`rotation`) and hides "Log done".
93. **Swaps and waxes from the rotation count after that day's rides**: a date alone means the start of
    the day, which would move that day's rides to the new chain. The one-click swap sends the current time;
    the Wax chains form sends the end of the chosen day (now, for today).
94. **Groupset actions follow how a bike is built** (Dirk 2026-10-26): Add groupset is a first-setup
    shortcut (Installed now, only while the bike has no groupset parts); afterwards a groupset is changed
    part by part (Change parts → Change a groupset part = normal Replace) or as a whole (Replace whole
    groupset = the same import with occupied positions replaced, old parts stored with their km).
    Manage parts is grouped Add / Remove / Change; Remove a part reuses RemoveForm.
95. **Delete only what has no history; everything else is retired** (inv.delete_bike / retire_bike /
    restore_bike): a bike counts as empty when it has no rides, installations, maintenance events,
    journal entries or usage (inv.bike_history_counts), which matches the trg_bike_no_delete trigger.
    Deleting removes its own settings rows (starting km, bike rules, snoozes, compatibility), unlinks work
    sessions and chain rotations, writes a DELETED change-log row, and adds its Strava gear id to the
    setting strava_ignored_gear, which the gear mapper skips so a sync never re-creates it. Retiring can
    take the parts off into storage in one work session.
96. **Frame and fork are parts; the bike is the build** (Dirk 2026-10-26, services/frames.py, migration
    0014): catalog types FRAME and FORK, component.warranty_until, disposition WARRANTY_RETURN.
    `ensure_frames` gives every active bike both parts (on create, at start-up, after imports and Strava
    sync) installed at the bike's first day (purchase, creation, first ride or starting km, whichever is
    earliest) with the bike's STARTING adjustment copied. While that automatic installation (note
    AUTO_NOTE) is the part's only one it follows the bike's start back when older rides arrive; a real
    swap is never touched. Automatic installations do not count as bike history (delete stays possible),
    frame/fork are left out of unpriced-part warnings (they came with the bike) and of change notices when
    other parts changed. Retire with parts off keeps them on the bike. `frame_history` lists bike-level
    FRAME_INSPECT events and CRASH incidents inside the part's installation periods.
97. **Sending a part away is a service order, for any part** (Dirk 2026-10-26, services/service_orders.py,
    migration 0015): service_order keeps where the part came from (bike or parent part and slot), shop,
    reason, linked incident, and the return (outcome, cost, receipt, notes, replacement). Sending removes
    it with outcome AWAITING_SERVICE (no km while away). Four outcomes are kept apart: REPAIRED_PAID,
    REPAIRED_WARRANTY, REPLACED_WARRANTY (new part created in the return session; old part
    WARRANTY_RETURN, keeps its km), NOT_REPAIRED (stored or discarded). The cost is a REPAIR maintenance
    event with the bike it came from, so bike costs count it once. Putting it back replaces a part fitted
    meanwhile (stored). The linked incident's entries for the part (or the whole-bike entry) get the fix;
    it is solved when every entry is fixed. Both steps are work sessions; undo voids or reopens the order
    (clear_for_session). Rides on a bike that had a frame/fork but has none that day get NO_FRAME/NO_FORK
    flags; the bike is not blocked (the ride date may simply be wrong).
98. **Frame and fork are one piece** (Dirk 2026-10-26): only FRAME is added automatically (type name
    "Frame and fork"); FORK stays as an optional separate part type so existing data keeps working.
    frames.drop_auto_forks (run by ensure_frames) removes a fork whose only record is the automatic
    installation (no other installation, work, journal, status, repair, price, serial, warranty, product,
    note or mark): its usage rows and starting km go with it. No NO_FORK ride flag.
99. **Part life and forecasts are computed, never stored** (Dirk 2026-10-27; services/part_life.py,
    maintenance._forecast). A part is finished when its disposition is out of use for good (OUT_OF_USE);
    its life runs from the first installation to the last removal (else the retire date); km, hours and
    certainty come from component_usage, so starting values and uncertain rides show as ≈ / ≥. Parts
    never installed are left out; frame/fork too. The forecast uses the subject's km (or ride hours) over
    the last 28 days, or since the reminder's count started if that is later; it needs at least 3 rides
    and 7 days, otherwise it says why there is none. It is a separate `forecast` field: status and
    explanation still go by the km actually ridden. A months limit that comes first is named.
100. **Look and feel: sporty activity-feed style, our own branding** (Dirk 2026-11-01, "make our app look
    similar to strava.com"). Top bar with text navigation (bottom tab bar on phones), light grey page, flat
    white cards, one orange accent (`--accent`) for the main action, active tab/nav and chips, blue links,
    big stat numbers with small grey labels. A similar feel, not a clone: own logo, name and colour values;
    no fonts, icons or assets from another app. Only CSS and the page skeleton changed. docs/ui-style.md.
101. **Always light, white page** (Dirk 2026-11-01: "the background color is still dark, change it to
    white"). No dark mode: the `prefers-color-scheme: dark` block is gone and `:root` sets
    `color-scheme: light`; `--bg` is white.

102. **A groupset can be added from Add part too** (Dirk 2026-11-01): "Groupset" is a pseudo-type at the
    top of Add part's type list (not a component type: a groupset stays a view of its parts, DECISIONS
    91) and renders the same GroupsetImport as the bike page, with the bike picker (or none = spares).

103. **Maintenance log entries can be edited and deleted** (Dirk 2026-11-01: "edit and delete buttons
    to remove log entries"). Delete is a void like everywhere else (no hard deletes): `voided_at` +
    reason "deleted", its supply transactions are voided with it (stock comes back), reminders and costs
    no longer see it, and Restore un-voids both. An entry taken back by Undo of its work session cannot
    be restored on its own (use the session). Edit changes only the descriptive fields (date, cost,
    symptom, work done, outcome, measurement, notes); which part, which action and which supplies were
    used are fixed: delete and record again. Changed, deleted and restored entries write change-log rows
    (ENTRY_CHANGED / ENTRY_DELETED / ENTRY_RESTORED) on the part, or on the bike for a whole-bike entry.
    Add part has Save / Cancel, both returning to the Inventory list (Dirk: "so the view goes back to
    the inventory screen").

104. **Breadcrumbs follow the way you came** (Dirk 2026-11-01: "how do i go back?"). Shown on every page
    below a main menu item (part, bike, groupset pages), above the page. Each page you open from another
    page is added; a main menu item starts a new trail; opening a page that is already in the trail (a
    crumb, the browser's back button) cuts the trail there. The tab you were on is a crumb of its own
    (Inventory › Installed, TIME NXR › Rides) so going back opens that tab. Opened directly, or straight
    from the main page it lives under, a page gets the trail of where it lives (Bikes › bike › Groupset).
    At most 7 steps (older middle steps drop). Logic in `frontend/src/crumbs.ts` (pages name themselves
    with `useCrumb`), shown by `components/Breadcrumbs.tsx`; trail and names kept in sessionStorage for
    the browser tab only.

105. **Same name for a second identical part** (Dirk 2026-11-01: a spare bottom bracket with the same
    label was refused). Every physical part is its own record, so a name already used by a part of that
    type no longer blocks Add part: `inventory.free_label` saves it as "name (2)", "(3)", … (the same
    numbering replacements and groupset imports already used). Labels stay unique per type, so every
    list, picker and import still tells the parts apart. Renaming onto a name in use is still refused,
    with a hint.

106. **Pick lists, shops first** (Dirk 2026-11-01: where a part was bought, a dropdown of shops, and a
    place in Settings to manage such lists). Records keep the shop name as text in their own column
    (`shop` on bike, component and consumable_txn, new in migration 0016; `merchant` on bundles and
    `shop` on service orders already existed). `pick_list_item` holds the names on offer per list.
    A before_flush hook (`services/picklists.py`) stores every name as the list spells it, adds new
    names, follows merges and unhides a hidden name used again, so typing never creates near-duplicates.
    Rename and merge rewrite the records through the ORM (change log rows); merged and hidden entries
    stay (no deletes). A new list = one entry in `LISTS` naming its columns; API, hook and Settings →
    Lists pick it up. Text instead of a foreign key keeps every existing record, import and export as it
    was.

107. **One short way to install a tire** (Dirk 2026-11-01: "installing tires is clumsy and broken").
    Before, a tire went on only through bike → Manage parts → Install a part, and only if it was already
    in storage; a stored part's own page had no Install, and "Swap tire" was greyed out until a tire was
    on. `components/InstallHere.tsx` asks where (positions from `/api/mount-targets`, now with `under`
    = only positions on that part or parts mounted on it, and `occupied_id` / `parent_type` per target),
    a spare from storage or a new part (created and installed in one call), and the date. Used for
    "Install a tire" (wheelset/wheel page, bike page) and "Install" on a stored part's page. A taken
    position offers "Change it" = the normal Replace of the part that is there.

108. **A wheelset always has a front and a rear wheel** (Dirk 2026-11-01: "nothing where I can select
    front or back"). `services/wheels.py` `ensure_wheels` adds "<wheelset> front wheel" / "rear wheel"
    inside a wheelset that never had a wheel in that position, installed from the wheelset's first day
    with its starting km; run when a wheelset is added (API) and at every start. Install a tire offers
    new / used (km from before → prior usage RECORDED with a starting value, an estimate) / spare, and
    "Move the front tire to the rear wheel" / "Swap front and rear" through the existing move (swap)
    service. Installs dated today happen now (a tire taken off earlier today frees the position first).
109. **Broken spokes are logged on the wheel** (Dirk 2026-11-01: "a way to log when a spoke breaks ... and
    when it got replaced ... an alert when the 3rd spoke broke"). A break is a "Broken spoke" incident on
    the wheel (`services/spokes.py`: log_broken, mark_replaced, remove_broken; API
    `/api/components/{wheel}/broken-spokes`), replaced through the incident fix (repairs.fix → SPOKE_REPLACE
    event, stock use, undo). `maintenance.spoke_breaks` lists breaks (incidents plus SPOKE_REPLACE events
    logged on their own, not double counted: an event whose work session fixed a spoke incident on this
    wheel belongs to it). The count since lacing now counts breaks, not replacements; at the limit
    (default 3) the reminder reads "Replace the wheel (or re-lace it)", and an unreplaced spoke is
    ATTENTION. The spokes' install date defaults to the wheel's purchase date (`laced_on`).
110. **Di2 wires and junction boxes are groupset parts** (Dirk 2026-11-01: "the di2 wires are part of the
    groupset"). New types DI2_WIRES (slot DI2_WIRES) and DI2_JUNCTION (slot DI2_JUNCTION), category
    Controls, so `assemblies.in_groupset` and the bike page's Groupset group include them. Groupset
    templates use DI2_WIRES. Migration 0017 retypes existing OTHER parts (and their products) that sit in
    the DI2_WIRES slot or are named Di2 wire / EW-SD… (wires) or junction / EW-JC… / EW-RS910 (junction);
    the bike-level "Inspect Di2 wires" reminder is unchanged. 12-speed Di2 (R9200, R8100, R7150, GRX
    RX825) has no junction box: charging is at the rear derailleur port (Dirk 2026-11-01), so
    DI2_JUNCTION is named "(11-speed Di2)" and no 12-speed template adds one.
111. **Part properties are edited in the app** (Dirk 2026-11-01: Cockpit and wheelset properties).
    `meta.component_types[].specs` sends each type's fields (product_specs.fields_for: type fields,
    torque, weight / colour / material). Add part (`components/Properties.tsx` SpecInputs, `specs.ts`)
    saves them as the part's own specs; the part page's Properties card shows own values over product
    values and edits them with notes (PATCH keeps spec keys that are not fields of the type). New type
    COCKPIT (category Cockpit, slot COCKPIT, torque) for one-piece / semi-integrated bar and stem;
    integration is an enum. Wheelset: rim_outer_width_mm, internal_width_mm (label "Rim inner width"),
    rim_depth_front_mm / rim_depth_rear_mm (front and rear can differ, Dirk), tire_size_range (text).
    fields_for drops a common field (weight, colour, material) when the type has its own with that key.
112. **Install a part creates new parts too** (Dirk 2026-11-01). `InstallForm` (Bikes.tsx) offers "A new part"
    (Inventory's `ComponentForm` with `bikeId`: mount targets of this bike only, a position required,
    "Save and install" → one POST /components with install) or "A part from storage" (`InstallStored`).
    Default: storage when there are stored parts, else new.
113. **The frame in Costs** (Dirk 2026-11-01). `costs.first_frame` = the bike's earliest FRAME installation.
    No bike purchase price and a priced, non-bundle first frame → that price is the initial cost
    (`initial_source` FRAME, not in parts). With a bike purchase price the first frame is INCLUDED (not
    counted). A later frame counts as a part (PART) for the bike it was first installed on. `cost_detail.frame`
    carries the row; the Costs card shows it with a "Frame price" sheet (PATCH components/{id} price, date,
    shop). Bundle items carry `groupset` (link to /bikes/{id}/groupset) or `component_id`.

114. **A wheel's built-in parts are included in a priced wheelset** (Dirk 2026-11-01). `costs.BUILT_INTO_WHEEL`
    (wheels, hub, hub bearings, spokes, rim, rim tape) without own price, inside (now or before, any level) a
    part with a price or a live bundle (`_in_priced_parent`), are not listed as "no price". Parts bought on
    their own (tire, tube, cassette, rotor) still are.

115. **Groupset as a tree under Installed now** (Dirk 2026-11-01). `SetupGroups` (Bikes.tsx) splits the GROUPSET
    rows by the catalog category of each top-level part (`GROUPSET_SUBS`: Drivetrain, Controls shown as
    "Shifting and controls" with the battery, Brakes) into nested `details.setup-sub`, folded like the rest.
    Frontend only; e2e helpers unfold `details.setup-sub` too. Header rows have no links (Dirk): "Groupset N parts ·
    name" like "Wheels and tires N parts · …"; the groupset page link is inside the unfolded group.

116. **Who did the work** (Dirk 2026-11-01). `maintenance_event.shop` (migration 0018), on every entry of a
    batch, editable (EDITABLE), in the SHOP pick list's columns (rename/merge follow). Empty = done yourself.
    LogMaintenance and EventLog's Edit use ShopPicker ("Done by a bike shop (optional)"); Costs SERVICE items
    read "Action (Shop)".

117. **Puncture statistics** (Dirk 2026-11-01). services/punctures.py, GET /api/reports/punctures, Rides tab
    Punctures (components/Punctures.tsx). One puncture = one wheel of a live FLAT incident. Tube/tire = the
    damaged part of the incident, else the one on that wheel that day (`_wheel_of` via installations, the
    removal day included). Model = product maker+model, else the label without " (n)". Stock tubes have no
    record: a flat on an unrecorded tube is the stock line the previous fix on that bike+wheel put in
    (ConsumableTxn USE of the fix's work session, note ": front …"/": rear …"), km = bike ride km between.
    Computed on each call, nothing stored. Logging stays where it was: the ride → Add incident → Flat tire.

118. **Ride notes** (Dirk 2026-11-01). `ride.notes` existed (API, not shown). Now: `rides.RIDE_NOTES_MAX` = 2000,
    trimmed, longer is refused; not a SOURCE_FIELD, so Strava/CSV re-sync never touches it. UI: `RideNotes`
    section on the ride (Rides.tsx), snippet in the ride list.

119. **Strava: known bikes only** (Dirk 2026-11-01). Setting `strava_known_bikes_only` ("0"/"1", editable; PATCH
    /api/settings). On: `_gear_mapper(create=False)` still links a same-name bike without gear id but never
    creates one; an activity with no resolved bike and no RideSource yet is skipped (count
    SKIPPED_UNKNOWN_BIKE, cursor still advances). Already imported rides keep being updated. Re-read
    (rescan) picks skipped rides up once the bike exists. UI: switch in StravaSettings (shown connected or not).
121. **Screen order** (Dirk 2026-11-01). Main screens go: needs doing → current state → history. Reminder grouping
    is one component, `GroupedTasks` (components/TaskList.tsx): OVERDUE/DUE/ATTENTION open (plus DUE_SOON,
    except on the overview where `foldSoon` folds it), SNOOZED / INSUFFICIENT_INFO / the rest in
    `details.task-group` (data-group soon/snoozed/first/ok). Used by Overview, Maintenance and the bike page.
    Explanations clamp to two lines (`Why`, ResizeObserver decides whether "more" shows); the full text stays in
    the DOM. Part page: rare actions in `details.more-menu`; ledger in `details[data-group=ledger]`. Overview
    bike tiles `.bike-strip`. No endpoint or function was removed.

120. **GitHub Releases for friends** (Dirk 2026-11-01). `.github/workflows/release.yml` on `windows-latest`,
    started by a pushed tag `vX.Y.Z` or by Run workflow (the cloud cannot push tags, Dirk prefers buttons). The
    version comes only from `__init__.py`; the workflow tags locally before PyInstaller so the build is the plain
    release version, and `gh release create --target <sha>` creates the remote tag. Before publishing it installs
    the setup silently, starts the app, adds a bike, installs again over it and checks the bike is kept (this is
    the CI proof of "updating keeps data"). Release text = docs/INSTALL.md + the version's CHANGELOG part (folded),
    so friends can read it without repo access. Optional other target repo (`RELEASES_REPO` + `RELEASES_TOKEN`)
    because releases of a private repo are not downloadable by others. Replaces packaging/ci/windows-build.yml.example.

122. **Lubrication entries are product only** (Dirk 2026-11-02). LogMaintenance hides Amount and Cost for actions
    of kind LUBRICATE (hot wax, liquid wax, lube) and lists only WAX/LUBE/OTHER supplies; hints link to
    Inventory → Supplies and Settings → Lists (ShopPicker `hint`). The API still accepts amount and cost.
123. **Change log shows names, not ids** for bike references (`changelog._BIKE_FIELDS`: rotation_bike_id);
    `entries` turns a bare id stored earlier into the bike's name when shown.
124. **Bulk remove / restore rides** (Dirk 2026-11-02). `rides.remove_rides` / `restore_rides` (POST
    /api/rides/remove and /api/rides/restore, `ride_ids`, dry_run, op id) loop the single-ride exclude/restore,
    so the rules stay identical: soft, restorable, never re-imported, km recalculated. The UI sheet runs a dry
    run first to show the part km change. In Removed rides only user-removed rides (not "deleted at source")
    can be ticked. No hard delete.
125. **Inner tubes are tracked parts once a wheel is recorded** (Dirk 2026-11-02: "install a tube and from that
    point on the mileage should be counted"). `repairs.replace_at_position` draws a part from stock
    (`stock.draw_component`, label = the stock name unless it has a product) or creates a new one for tubes as
    for tires, installed at `<day>T23:59` for a date alone (after that day's rides). Without a recorded wheel it
    stays a stock use (punctures still infer the model from the last fix). InstallHere has a "From stock"
    source (POST /api/consumables/{id}/install). `punctures._collect` ignores parts put in by the flat's own fix.
126. **Puncture stats per tube / tire, not per model sum** (Dirk 2026-11-02). `punctures._by_model` returns per
    model `punctures` and `items` (component_id, label, km, punctures, km_per_puncture, in_use); stock tubes without
    a record are one item "From stock (no record of its own)" with the inferred km. Replaces DECISIONS 117's
    summed "km per puncture per model".
127. **Wheel page: Tire and inner tube** (`wheels.tire_and_tube`, `tire_tube` in GET /api/components/{id} for
    FRONT_WHEEL/REAR_WHEEL): per kind current + history from installations on that wheel; km_here = counted
    usage between install and removal, km_total, punctures = FLAT incident groups on that part, ended = removal
    reason + disposition. Parts drawn from stock without a product take the stock line's name (`stock._stock_label`).
128. **Delete a bike for good** (Dirk 2026-11-02). The history tables are append-only by database triggers
    (maintenance, journal, change log, bike with rides), so `services/bike_purge.py` does not wipe rows: it sets
    `bike.deleted_at` (migration 0019), status RETIRED, frees the name ("X (deleted <date>)"), clears and ignores
    the Strava gear, excludes its rides, takes its parts off into storage (or RETIRED) with a CORRECTION of the km
    they did on it, and every list hides it (`/api/bikes`, `list_rides`, `all_incidents`, punctures). The API
    (POST /api/bikes/{id}/purge, confirm_name) takes a kept backup first. Retired bikes are off the overview.
129. **Tires and inner tubes share names; chains get letters** (`catalog.SAME_NAME_TYPES`, `LETTER_TYPES`;
    `inv.free_label`, `_next_label`). Migration 0020 rebuilds `component` (SQLite cannot drop a table constraint):
    the unique (type, label) becomes a partial unique index without TIRE/INNER_TUBE; existing "(n)" suffixes are
    removed for tires/tubes and become letters for chains. `migrate.upgrade_database` now runs migrations with
    foreign keys off and `PRAGMA foreign_key_check` before the commit (SQLite's documented rebuild procedure).
130. **Defect tube / tire and install from a wheel**: `tire_and_tube` rows carry `defect` (a FLAT entry on the
    part with no repair or "Nothing yet"); InstallHere opened on a wheel page lists only that wheel (`under`
    = the wheel), and an occupied position explains "already has X … Replace X".
131. **Chains offered for a rotation** (Dirk 2026-11-02: "no stored chain … but there should be 2 chains"): a
    chain joins the rotation of the first bike it goes on and stayed there after coming off, so it was never
    offered on another bike; chains in counted stock were not offered at all. The picker now offers every
    active chain on no bike (one from another bike's rotation says "moves here"), and chain stock lines
    ("from stock, N left": one unit is taken out of stock and gets its own record). Chains not offered are
    listed folded under "Other chains" with where they are (on another bike, retired).
132. **The mark is part of the name** (Dirk 2026-11-02: renaming a chain to the same name with mark "A" was
    refused; "list it in the system as Shimano XT CN-M8100 12-fach Kette [A] … same logic to tires").
    `component.label` stays the one name shown everywhere and is now "name [mark]"
    (`inventory.with_mark`, `strip_mark`, `name_of`); no new column, so every list, picker and report shows
    the mark without changes. Uniqueness per type (not tires/tubes) therefore means name + mark. A second chain
    of the same name gets the next free letter as its mark (a chain without a mark counts as A); this replaces
    the "(B)" suffixes of 129 (migration 0021 turns "Name (B)" into "Name [B]" with mark B and appends existing
    marks). Marks are at most 20 characters (checked when changed) and contain no brackets. Other part types
    still get "(2)" for a repeated name without a mark.
133. **Hot wax after a liquid-wax top-up** (Dirk 2026-11-02: "300km hot wax, followed by a liquid wax top-up,
    then a fresh hot wax after another 200km … sometimes … a liquid wax top-up and then a fresh hot wax after
    200km"). This replaces "a top-up never postpones the hot wax" (acceptance 2 of the brief, now changed): the
    hot-wax rule has `after_top_up_km` (default 200, migration 0022 sets it on every WAX_HOT rule); with a
    top-up after the last hot wax the hot wax is due at (km at the top-up + after_top_up_km), otherwise at
    interval_km. So a top-up can bring the hot wax forward or move it later. Empty = old behaviour.
    `chains.chain_history` lists `top_ups` [{date, at_km}] per cycle and, for the current one,
    km_since_top_up / hot_wax_due_at_km / hot_wax_left_km; the rotation timeline has kind TOP_UP.
134. **Service intervals and charging** (Dirk 2026-11-02 batch). Most of the batch existed: bar tape is a part
    type (product = brand + model, price, bought on/from, install date; km and now ride hours on the part
    page), "Add km from before" gives pedals their km from a previous bike, brake fluid is the BRAKE_FLUID rule
    on each hydraulic brake circuit (24 months), and the charge reminders were set on 2026-10-26 (Assioma
    80 h; Di2 BT-DN300 800 km). Researched again: BT-DN300 about 1,000 km per charge on most retailer pages
    (front shifting uses most), Assioma PRO RS at least 60 h, 160 h after Favero's 2026 firmware update; both
    retailer-sourced, not verified with the makers, so the defaults keep a margin. New: Settings → Service
    intervals edits the type defaults (PATCH /api/rules/{id}; GET /api/rules adds `own_values`, the number of
    part/bike overrides), and `maintenance.charge_history` (component detail `charging`) lists charges with
    km / ride hours / rides / days between them.
135. **One row per wax application** (Dirk 2026-11-02, table agreed in chat before building).
    `chains.wax_applications(comp)` (component detail `chain.wax`): applications newest first with n (oldest =
    1), type, product (the event's supply), at_km (km since the last hot wax; hot wax = 0; top-up before any
    hot wax = none), ridden_km and days_on while it was the latest, active, ended_by {n, type}, and next_due
    on the active row only (after a hot wax: top-up window and hot wax; after a top-up: hot wax, from
    chain_history's due km). `current` feeds the "Current:" line. chain_history stays for the API and rotation.

136. **No personal name in the shared app** (Dirk 2026-11-02). Publisher / CompanyName = "Bike Log" in
    bikelog.iss and bikelog.spec; the release workflow comment uses `<owner>`. Dirk may rename his GitHub
    account to hide his real name; nothing in the code depends on the owner name except docs/clone URLs.

137. **Wet ride asks for a liquid wax top-up** (Dirk 2026-11-02: "if it rains and i flag a ride as wet, will i
    get a reminder to use liquid wax top up?"). Before, a wet ride made the hot wax due. Now `_cycle_status`
    of the WAX_LIQUID rule is DUE with "Top-up recommended: wet ride on <date>" when a wet ride came after the
    last top-up (or the hot wax) of the cycle, even outside the 250–300 km window and even if a top-up was
    done earlier in the cycle; `_add_wet_ride` skips WAX_HOT while that rule is on. A top-up logged with a date
    only sorts at 23:59:59 that day (`_event_sort`), so the wet ride's km stay before it and the hot wax falls
    due after_top_up_km after the top-up, not after the start of the day.

138. **Self-hosted server mode, single user, Google sign-in** (Dirk 2026-11-02: "i want to host it online, as
    cheap as possible. but with a google account login"; reverses "desktop-only for now"). Same app and
    SQLite database started with `--server`: Google OpenID Connect (scope `openid email`, no Google API
    access), allowlist `BIKELOG_ALLOWED_EMAILS` checked again on every request, HMAC-signed session cookie
    (30 days), CSRF token derived from the session, Host check against the public domain. Everyone on the
    allowlist shares one database; the multi-user design of the 2026-10-26 assessment is NOT built.
    Deployment: Docker Compose (bikelog + Caddy for Let's Encrypt), cloned from the private repo with a
    read-only fine-grained token, nightly `bikelog-update` from main (opt-in). Off-server backups = Hetzner
    server backups + Download in Settings. Location: Germany (Hetzner). Dirk asked about hosting outside the
    EU "so i dont get into trouble with strava": server location changes neither the Strava API terms (they
    bind the developer) nor GDPR (household exemption for own data; and it follows the EU resident anyway),
    so the choice is cost and latency. New databases on a server start empty (no sample); data moves by
    uploading a desktop backup (Settings → Backups → Bring data from another computer → Restore).

139. **PHP + MySQL multi-user web version, separate from the Python app** (Dirk 2026-11-02: "make a php
    version of the software. and remove the strava stuff for now. we add rides manually via a form. and add
    user management ... it needs to be secure. and i need an admin page"; then "we need to use mysql"; on the
    decision card he chose "Full feature match" over a lean first release). Built in `php/` of the same
    repository: plain PHP 8.1+ without framework or Composer (runs on cheap shared hosting, upload by FTP),
    MySQL/MariaDB through PDO prepared statements, server-rendered forms, `?r=<route>` URLs (no rewrite
    rules needed). Every bike table has `user_id` and every query filters on it. Accounts: Argon2id,
    email confirmation, reset links (SHA-256 stored, single use, 1 h), invitations, rate limits in MySQL,
    audit log, admin role; deleting an account is a real delete (GDPR), everything else is voided, not
    deleted. Catalog shared with Python through `scripts/export_php_catalog.py` → `php/app/catalog.json`.
    Simplifications in the base (to be closed by the full port): date-only installations and rides (no
    times), no usage profiles (indoor rides skip wheels/tires/tubes/rotors/pads), CYCLE_WINDOW rules become
    an interval at the window end with the window as warning, PARENT_COUNT rules not yet, no cached totals.
    Rides on a maintenance day count as after it (reminder slightly early, never late). The Python desktop
    app and its server mode (138) stay unchanged.
    Round 2 (migration 002) follows the desktop rules: work sessions make a groupset import or an incident
    fix undoable in one step (parts it created are deleted, installs voided, removals reopened); removed
    parts get a disposition (STORED, AWAITING_SERVICE, DISCARDED ...; discarded/sold/retired retire the
    part); counted stock is a consumable line with `tracking_mode = COUNTED` and a part type, and taking one
    out creates an individual part in the same transaction; spare minimums, spoke limit and default tire
    setup are per-user settings (`user_settings`); incidents are journal entries sharing `incident_group`,
    one per affected part or position; punctures list each tire or tube with its own km, never summed per
    model. The auto frame part does not stop a bike without other history from being deleted.
    Round 3a (migration 003) adds the rule kinds CYCLE_WINDOW and PARENT_COUNT and the hot-wax
    after_top_up_km, and converts the base release's stand-in (liquid wax as "interval 300, warn 50") into
    the 250–300 km window. With dates only, a wet ride counts against a wax from the next day on (a wax
    logged on a day was done after that day's ride), as in the desktop app.
    Round 3b (migration 004): costs follow costs.py (a part counts for the bike it was first fitted to, a
    bundle once for the bike most of its parts went on, stock at its average purchase price as an estimate,
    services from maintenance cost; a part drawn from stock is linked by `from_stock_txn_id` and has no own
    price). Sending away and the return are work sessions, so Undo voids the order or reopens it. The pace
    forecast uses the last 28 days (at least 3 rides over 7 days) and is planning help only.
    Round 4a (migration 005): the product import is a port of product_import.py with the same format and
    rules; spec fields come from product_specs.py through catalog.json (scripts/export_php_catalog.py).
    Checked files wait up to an hour in `storage_dir/imports` under a random token, so "Import" needs no
    second upload. Shop names and the change log hang on two hooks in `Db::insert` / `Db::updateOwned`
    (`Db::$beforeWrite`, `Db::$afterWrite`, set by `ChangeLog::register()`); raw `Db::run` statements
    bypass them, so removals, voids and undo write an explicit `ChangeLog::note`. The change log is
    information only, never used for totals.
    Round 4b: per-user backups are gzipped exports in `user_backups` (newest 20 kept). A restore checks the
    whole file first (every reference must point to a row in the file, required fields present), then in
    one transaction stores a copy, deletes the user's rows and inserts the file's rows with new ids above
    each table's current maximum (`UserBackups::TABLES` lists every reference column; change_log.entity_id
    follows its entity). It never re-adds default rules, so a rule the user deleted stays deleted. Fresh
    start = copy, delete, default rules. "Indoor" is the desktop app's DIRECT_DRIVE_TRAINER usage profile
    (wheels, cassette, tires, rotors, pads excluded); ride start times were already there.
    Round 5a (migration 006): a part's km come from "usage periods" (Domain::usagePeriods): fitted on a bike
    (minus rides that set that wheel position to something else in ride_equipment), worn by the rider
    (shoes with disposition IN_USE, as allocation.py's rider index), or picked for a ride; parts hanging on
    another part inherit its periods. All periods are OR-ed into one query, so a ride counts once. A ride
    left out of the km (rides.excluded_reason) counts nowhere (Domain::COUNTED). CSV import identity is
    (source_kind, source_ref); a ride imported before is never touched again (local edits win, removed
    stays removed), a simplification of imports.py which updates source values under local overrides.
    Round 5b (migration 007): `Workshop` (php/app/workshop.php) ports inventory.replace, group_wheels,
    spares.replace_options/compatibility and maintenance.brake_overview/charge_history. A replace is one work
    session: carried children are taken off the old part and refitted on the new one; a carried child whose
    position the chosen spare already fills stays on the old part (the desktop app refuses instead; the web
    form says which ones stayed). ensureWheels runs after a wheelset replace, so a new wheelset only gets
    wheel records when the wheels did not move over. Fits live in `product_bike_fit` (VERIFIED/UNVERIFIED,
    SAME_PRODUCT and UNKNOWN are derived). Charge gaps use Domain::rideUsage with an until date (rides on
    the day of a charge count after it). A voided entry and its supply use get the same voided_at so a
    restore brings back exactly those; an entry voided by an undo cannot be restored.
140. **English and German in the PHP web version** (Dirk 2026-11-03: "we also need to be able to switch
    languages. we need the whole app in german aswell"). The English text in the code is the translation
    key: `t('English {placeholder}', [...])`, German in `php/app/lang/de.php` (informal "du"); a missing
    German text falls back to English instead of failing. Language order: users.lang (migration 008, set by
    the DE/EN switch in the top bar or My settings) → cookie `bikelog_lang` (visitors) → Admin setting
    `default_language` → Accept-Language → English. The command line (tests, tools) is always English, so
    existing tests keep checking English texts. Catalog names (part types, actions, slots, labels) are
    translated where they are shown; German noun plurals come from `plural:<English>` keys. What users type
    is stored and shown as typed; rule names created by the app in English are translated on display. Kept
    in English on purpose: the per-field messages of the product JSON check, the script instructions
    (AGENT_INSTRUCTIONS.md, schemas, examples) and the CSV column names, because they are read by scripts
    and developers. `php/tools/i18n_keys.php` lists every key; test_95 fails on a missing German text, wrong
    placeholders, an unused German entry or English UI text left on a German page. Numbers on screen use a
    decimal comma in German; number fields accept both. The Python desktop app stays English only for now.

## Repository
27. Pushed only to the feature branch `claude/project-thread-6y3mmh` of the private repository. Demo
    data uses fictional Strava gear ids.
