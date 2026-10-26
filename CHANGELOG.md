# Changelog

What changed in each Bike Log version. Versions are MAJOR.MINOR.PATCH: PATCH = fixes only, MINOR = new
features, MAJOR = big changes (for example to the data format). A build between releases shows its commit
after a plus sign, e.g. `0.2.0+abc1234` = version 0.2.0 plus later changes. How to make a release:
UPDATING.md → "Making a release". New entries go under "Unreleased" as work is done.

## Unreleased

### Added
- Ride incidents reworked: each kind of incident offers only what it can affect, taken from the parts on
  the bike that day (flat tire → front / rear tire; shifting → front / rear derailleur, shifters ...;
  empty battery → Di2, power meter, head unit, speed or cadence sensor ...; fitting problem → numb hands,
  back pain ...). New kinds: shifting, dropped or broken chain, brakes, empty battery, loose or slipping
  part, creak or noise, wheel, pedal or cleat, fitting problem. Tick several (two flats, both
  derailleurs). Incidents can be edited on the ride, and removed and restored (never deleted).
- Ride page: each incident shows open or solved, with a "Solved" button (records today's date) and a
  "Re-open" button that makes it open again. "Fixed" is now called "solved" everywhere.
- Ride page: "Distance and time" shows a short summary (this ride; the bike in total, this year and this
  month, each in km and ride hours). The parts list unfolds with "Show details" and has an hours column.
- Bike page tidied into tabs: Parts and service, Incidents (with the number of open ones), Maintenance,
  Costs, Journal and history. "Installed now" shows one line per group (groupset, wheels and tires,
  cockpit, contact points, frame, electronics) that unfolds with the triangle. Service status shows what
  is due first; "Need a first entry" and "Up to date" fold away.
- Bike page → Rides: the bike's rides (date, name, distance, time, wet / incidents / indoor), with a
  total line; click a ride to open it right there.
- Bike page → Incidents: every incident on the bike with its ride, and the same Solved / Re-open, Edit,
  Remove and Restore as on the ride.
- Yearly full service: a whole-bike reminder every 12 months. "Log done" shows a checklist of the big jobs
  (hub bearings, headset, bottom bracket, brakes, Di2 wires / cables, frame and fork, drivetrain, pedals,
  torque); ticked and unticked jobs are saved with the entry. Each job keeps its own reminder on its part.
- Tire pressure note per tire (e.g. "4.8 bar"): set it on the bike page or the tire's page. A note only,
  no reminder.
- Groupset bought as one bundle: one price, shop and date for the whole set, counted once in the bike's
  running cost; parts replaced later get their own price. Bike page → "Bought as a bundle" lists what is
  in use and in storage, with an estimated share per part; existing parts can be grouped later.
- Groupset import: tick "spare" to keep a part in storage instead of installing it (e.g. a bottom
  bracket that does not fit); it stays part of the bundle.
- Settings → Fresh start: empty the database after typing RESET; a full backup is made first and kept;
  Strava stays connected unless you tick "Also clear the Strava connection". Every backup in Settings
  now has a Restore button (the current data is backed up first).
- Part page: "Add km from before" for parts that were ridden on other bikes; the date defaults to the
  day the part was first installed.

- Ride incidents: open a ride and log a flat, crash or defect, linked to the affected part; it shows on
  the ride, the bike, the part (and the wheel/wheelset above it) and in Rides → Incidents.
- Dry/wet per ride (never overwritten by Strava or CSV imports).
- Wheelsets as a group: bike page → "Group wheels into a wheelset"; wheels carry tires, tubes, hub,
  hub bearings, spokes, rim tape and a speed sensor, each with its own km. New part types WHEELSET, HUB,
  HUB_BEARINGS, SPOKES, RIM_TAPE, PULLEY_WHEEL (upper/lower on the rear derailleur), POWER_METER_PEDALS,
  SENSOR.
- Quick links move to the next chain at a chain change (tick box in Replace) and are due after 2 chains.
- Charging reminders with a "Charged" action: Di2 battery 800 km, power meter 50 ride hours, Assioma
  pedals 80 ride hours, speed sensor battery 400 h or 12 months; lever coin cells 24 months (off by default).
- Reminder rules can count ride hours or the number of parts served (rule editor).

- Whole-bike reminders: torque check every 3 months and once after the first ride on newly fitted parts
  (with the torque from the product spec), Di2 check and wire inspection (electronic shifting only). A
  crash asks for a frame and fork inspection (and a hanger check) until it is logged.
- Measurements set the result: pads 1.0 mm low / 0.5 mm at limit, rotors 1.6 / 1.5 mm (Shimano), chain
  0.4 % / 0.5 %. The form shows the result before saving.
- New reminders: bed in new pads and rotors, thru-axles every 6 months, yearly sealant clean-out and valve
  cores (tubeless only), pedal bearings, bottom bracket, bar tape, seatpost re-paste, derailleur hanger,
  brake hoses, cassette and chainring check after a worn chain, re-wax after a wet ride, tire check also
  yearly (age shown), charging for bike computer, lights and radar.
- New part types: stem, derailleur hanger, cycling shoes and cleats (count every ride on any bike while
  the shoes are in use), shift cable and housing (mechanical shifting only), tubeless valve, bike computer,
  light, radar.
- Shifting per bike (electronic / mechanical; not set = electronic when a Di2 battery is fitted) and a
  default tire setup in Settings (inner tube), so tubeless and cable reminders stay off where they don't apply.

### Changed
- Build output is quiet again: tests use `httpx2` (Starlette deprecated `httpx` for its test client),
  eslint 10 replaces the unsupported eslint 9 (same two hook rules as before), and esbuild's install
  script is approved in `frontend/package.json` (`allowScripts`, npm 11).
- Ride page in sections (Conditions, Incidents, Mileage given to parts); "Edit" is now "Edit ride".
- Assioma power pedals: charge reminder every 80 ride hours instead of 50 (your choice). Existing
  databases are updated unless you had changed the value yourself.
- Database schema 0005 → 0009 (upgraded automatically with a backup first).
- Lever coin-cell reminder 18 months (still off by default); rim-tape check for every tire setup.
- A quick link on a chain in storage reads "on Chain A (not on a bike)" instead of "unmounted parent".
- Ultegra R8100 groupset import adds upper and lower pulley wheels.

- A brand-new database starts with made-up sample data (Aurora SL with Ultegra Di2, Winter Allroad with GRX
  1×12, two months of rides, dry/wet, a flat, a crash and a creak) and a "Sample data" banner; Settings →
  Fresh start removes it. An existing database is never touched. `--no-sample` starts a new one empty.
- More groupsets to import (all 12 or 13 speed, hydraulic disc, specs marked unverified): Shimano Dura-Ace
  Di2 R9200, 105 Di2 R7150, 105 R7100 mechanical, GRX Di2 RX825 2×12, GRX RX820 1×12; SRAM RED AXS E1,
  Force AXS, Rival AXS, Apex XPLR 1×12 (AXS or mechanical), and the 13-speed RED XPLR and Force XPLR AXS.
  SRAM AXS batteries sit on the derailleurs and are charged every 55 ride hours.

### Fixed (imaginary-bike test run, B1–B15)
- A road ride on a bike with no wheels is flagged ("No wheels on this bike on the ride day").
- A service logged before a part's "km from before" date reads "at least N km since …"; a part with km
  from before but no service says so instead of "earlier history is unknown".
- Rides before tracking started explain why they add no km; rides dated before the bike's purchase date
  are flagged; the bike's ride count leaves out rides inside the starting km (shown as "+N before tracking").
- Time reminders of a new part count from the day it was installed, not the day it was bought.
- Groupset parts are named without the bike (the bike is added only when the name is taken); parts on a
  wheel show "since" the day they arrived on this bike.
- Replace → "New item, same product" takes a price; the cost card names the parts without a price.
- Starting stock of a supply is recorded as "Starting stock", not a purchase dated today.
- CSV import keeps an unknown bike name on the ride ("csv: Aurora (no bike with this name)") and lists it in
  the import summary; number errors read "distance_km 'abc' is not a number".
- Snooze counts days from the local date; readable supply kinds, units and slot names; "1 ride";
  the refused-undo message no longer says "fix and save again"; the sidebar shows the full version.
- The message after saving a ride is short ("+80.0 km on 20 parts"); the preview still lists each part.

## 0.2.0 (2026-10-25)

### Added
- Proper versioning: one version number for the app, the screens, BikeLog.exe (Windows file properties)
  and the installer (`BikeLog-0.2.0-setup.exe`); builds between releases carry the commit; this changelog;
  `scripts/release.py` to make a release.
- Settings shows the version, database schema and the commits of the app and the screens; a red bar warns
  when the screens are older than the app or an older copy is still running.
- One-step Windows build script `packaging/build.ps1` that stops at the first error.
- Tube/tubeless setting on wheels (moves with the wheelset), sealant top-up reminder every 3 months for
  tubeless tires, headset service reminder.
- Change log on every bike and part (old → new, when, who).
- Settings → Diagnostics: view and download the log, secrets removed.
- Headset and power meter part types.
- Rides area with tabs Rides / No bike / Removed rides; assign, change or remove the bike per ride or for
  several rides (kept on Strava re-sync); removed rides can be restored and are never imported again.
- Strava set up, connected, synced and disconnected from Settings (no command line).
- JSON product import with one template per part type, and instructions for scraper authors.
- Prices on parts, initial and running cost per bike, journal for bikes and parts.
- Groupset import with a Shimano Ultegra Di2 R8100 template.
- `UPDATING.md`: how to pull and rebuild on Windows.

### Changed
- Disconnecting Strava keeps all rides. Strava sync looks back 30 days so gear changes are picked up.
- Database schema 0003 → 0005 (upgraded automatically with a backup first).

## 0.1.0 (2026-10-25)

First build installed on Windows: bikes, parts and installations, rides and mileage, maintenance rules and
reminders (hot wax, liquid wax, chain wear, brake fluid, pads, wheels), spare parts and replacement with
undo, CSV import (including the Strava export), backups and export, demo mode. Database schema 0003.
Not tagged in git (it was built before versioning).
