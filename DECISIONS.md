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

## Repository
27. Pushed only to the feature branch `claude/project-thread-6y3mmh` of the private repository. Demo
    data uses fictional Strava gear ids.
