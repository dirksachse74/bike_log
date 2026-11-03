# Bike Log for the web (PHP + MySQL, several users)

A second version of Bike Log that runs on ordinary, cheap PHP web hosting. Everyone gets their own account
and only ever sees their own bikes, parts, rides and maintenance. The Windows desktop app (Python) stays as
it is; this folder is independent of it.

**Status (2026-11-02): work in progress, not released.** Dirk chose a full feature match with the desktop
app (minus Strava) before it counts as ready. The base is done; the remaining features are listed at the
end of this file and in TASKS.md.

## What it does now

- **Accounts:** sign up, confirm the email address, sign in, forgot password (link by email), change
  password / email, sign out on all devices, download all my data (JSON), delete my account.
- **Admin page** (Admin in the top bar, only for admins): user list with search; per user: send a password
  reset link, resend / mark the email confirmation, clear a sign-in lock, sign out everywhere, block /
  unblock, make admin / remove admin, delete the account. Invitations by email. Audit log of every sign-in,
  failed sign-in, reset and admin action. Site settings: who can sign up (anyone / only invited / nobody),
  allowed email domains, email confirmation on/off, maintenance mode, a notice for everyone. System:
  database updates, full SQL backup download, test email, clean-up. Admins see how many bikes and rides a
  user has, never the data itself.
- **Bikes and parts:** parts with only a type and a name; km before tracking (new / known / unknown);
  install on a bike or on another part (tire on a wheel on a wheelset); moving and replacing; "what was on
  the bike on date X"; wrong records are marked wrong, never deleted; retire; km corrections.
- **Rides** by hand: date, bike, distance (empty = missing, not 0), time h:mm, indoor/outdoor, wet/dry.
  Removing a ride hides it from all totals; it can be restored. Rides on a day when a part was changed are
  flagged.
- **Maintenance:** log what was done for a part or the whole bike; only the actions that fit the part are
  offered; measurements set the result (e.g. chain wear 0.5 % = at limit); supplies used come off stock.
- **Reminders** that explain their numbers ("545 km since new (fitted 2026-06-01), no hot wax logged yet
  (interval 500 km)"), km, months and ride hours, snooze without logging work, "not enough information"
  when the history is unknown, bad check results stay until a newer check. Intervals can be changed for a
  part type or for one part.
- **Supplies:** wax, lube, sealant, brake fluid... with bought / used / correction entries and stock.

The part types, maintenance actions and default intervals are the same as in the desktop app
(`app/catalog.json` is generated from `backend/bikelog/catalog.py` by `scripts/export_php_catalog.py`).

## What you need

- PHP 8.1 or newer with the extensions `pdo_mysql`, `mbstring`, `openssl` (almost every host has them).
- A MySQL 5.7.8+ / 8.x or MariaDB 10.3+ database (your hosting control panel creates it).
- HTTPS for your domain (most hosts give a free Let's Encrypt certificate with one click).
- An email account at your host or mail provider for sending (SMTP), e.g. `bikelog@your-domain`.

## Try it on your own Windows PC first

[LOCAL_TEST_WINDOWS.md](LOCAL_TEST_WINDOWS.md): XAMPP, one settings file, double-click `start-local.bat`.
Emails go to `storage/mail.log` instead of being sent.

## Install on shared hosting (no command line)

1. **Download the code:** on GitHub open the repository → green **Code** button → **Download ZIP**. Unpack
   it on your PC; you need the `php` folder.
2. **Create the database** in the hosting control panel (e.g. "MySQL databases"): a database, a user and a
   password. Note host, database name, user and password.
3. **Fill in the settings:** in `php/config/`, copy `config.sample.php` to `config.php` and open it in a
   text editor. Enter the database values, your web address (`base_url`), your email (SMTP) settings, and
   an `install_key`: any 24+ random characters (you type it once in step 6).
4. **Upload** the whole `php` folder with the host's file manager or an FTP program (e.g. FileZilla), for
   example as `bikelog/`.
5. **Point the domain at `bikelog/public`.** In the control panel set the document root of your
   (sub)domain to the `public` folder. If your host cannot do that, point it at the `bikelog` folder: the
   `.htaccess` file there forwards visitors to `public/` and blocks the private folders (Apache only).
6. **Open your address** in the browser. The install page asks for the install key, your name, email and
   a password. It creates the tables and your admin account and signs you in.
7. In **Admin → System** press **Send test email**. If it arrives, sign-up and password reset emails work.
8. In **Admin → Site settings** choose who may sign up. "Only people I invite" is a good start; invite
   friends from **Admin → Users**.

## Updates

Upload the new `php` folder over the old one (keep your `config/config.php`). If the update changes the
database, admins see a yellow bar "The database needs an update": **Admin → System → Download backup**
first, then **Update database now**.

## Backups

**Admin → System → Download backup** gives one `.sql` file with all accounts (keep it safe: it holds
everybody's data and password hashes). Restore it into an empty database with phpMyAdmin → Import. Each
user can also download their own data as JSON in **My account**. Use your host's backups as a second copy.

## Security in short

- Passwords: `password_hash` with Argon2id (bcrypt if the server lacks it), at least 10 characters;
  re-hashed automatically when the algorithm gets stronger.
- Every form carries a secret token (CSRF); all database queries are prepared statements; every page
  output is escaped; strict Content-Security-Policy (no inline scripts), no framing.
- Session cookie HttpOnly, Secure (with HTTPS), SameSite=Lax; new session id at sign-in; 12 h idle timeout;
  a password change, block or reset signs out all other devices.
- Sign-in limited to 5 failures per email and 30 per IP in 15 minutes; sign-up, reset and resend limited too.
- Sign-in, sign-up and "forgot password" answer the same whether an address has an account or not (an
  existing owner gets an email instead), and unknown emails cost the same time to check.
- Email links (confirm, reset, invite, email change) are random 256-bit tokens, stored only as SHA-256,
  usable once; reset links expire after 1 hour and the newest one replaces older ones.
- Every query that reads bike data is limited to the signed-in user's id; tests try to read and change
  another user's data and must fail.
- The install page needs the install key from `config.php` and refuses to run once an account exists.
- Private folders (`app`, `config`, `sql`, `storage`, `tests`) are outside the web root, plus `.htaccess`
  deny rules if they are not.

## Developer notes

```
php/
  public/          web root: index.php (front controller, ?r=<route>), assets/ (css, js, icon)
  app/             core.php (config, db, session, csrf, audit, rate limit, migrations), auth.php, mailer.php,
                   catalog.php + catalog.json, domain.php (installations, mileage), reminders.php,
                   inventory.php (spares, stock, work sessions), groupsets.php, incidents.php (journal,
                   incidents, fixes, punctures, spokes), chains.php (rotation, wax table), money.php (costs, bundles, repairs, part life),
                   products.php (products, JSON import), records.php (shop list, change log),
                   backups.php (per-user backup, restore, fresh start), rides.php (CSV import, bulk, wheels per ride),
                   workshop.php (replace with carry-over, wheels into a wheelset, product fits, brakes, charging),
                   pages/*.php (one function per route), routes.php, views/ (templates)
  sql/migrations/  NNN_name.sql, applied in order (install page / Admin → System)
  config/          config.sample.php (copy to config.php, never commit it)
  tests/           run.php + test_*.php (needs MySQL/MariaDB and the PHP built-in server)
```

Run the tests (they create and drop the database `bikelog_test`):

```
BIKELOG_TEST_DB_HOST=127.0.0.1 BIKELOG_TEST_DB_USER=bikelog BIKELOG_TEST_DB_PASS=... php php/tests/run.php
```

GitHub Actions runs them on MySQL 8 for every change to `php/` (`.github/workflows/php-tests.yml`).

Rules kept from the desktop app: installation periods start-inclusive, end-exclusive; a swap-day ride
counts for the part fitted that day and is flagged; part km = km before tracking + rides while on a bike
(directly or through a wheel / wheelset) + corrections, computed from history every time (no cached
totals); indoor rides do not count for wheels, tires, tubes, rotors and pads; a ride without distance is
missing, not zero; nothing with history is hard-deleted (wrong records are voided); a whole account is
deleted for real when its owner or an admin asks (GDPR).

## Still to port (full feature match)

Done in round 2: groupset import (with undo), punctures and incidents per wheel tube/tire, spares and
counted stock with the shopping list, spokes per wheel, frame + fork as one part, notes and issues.

Done in round 3a: chain rotation and the wax cycle (liquid top-up window, wet rides), quick link per chain.

Done in round 3b: purchase bundles and costs, repairs (send a part away), part life report and forecast.

Done in round 4a: products and the JSON product import (same files as the desktop app), the Shops list,
the change log.

Done in round 4b: backups and restore per user, fresh start, diagnostics, indoor = direct-drive trainer.

Done in round 5a: rides left out of the km, wheels picked for one ride, several rides at once, CSV ride
import, shoes in use.

Done in round 5b: replace a part (spare, stock, same product, new item) with what is mounted on it moving
along, wheels into a wheelset, which bikes a product fits, the Brakes page, symptom and work done,
restoring an entry marked as wrong, charge history.

Every desktop feature is now in the web version except Strava, which stays out for now.
