# Bike Log on your own server (with Google sign-in)

Bike Log can also run on a small rented server instead of your PC. You open it from any browser or
your phone at your own address, for example `https://bikelog.example.com`, and sign in with your Google
account. Only the Google accounts you list can get in. The desktop app keeps working as before.

**What it costs** (prices as of November 2026; check the provider's page, they change):

| What | Where | About |
|---|---|---|
| Smallest cloud server, Ubuntu 24.04, Germany | Hetzner Cloud (CX23 or CAX11) | €4–6.50 a month incl. IPv4 |
| Server backups (daily, kept 7 days, stored apart from the server) | Hetzner tick box | +20 % of the server price |
| A domain name | any registrar (Hetzner, INWX, Cloudflare, Porkbun…) | €1–15 a year |
| Google sign-in, HTTPS certificate (Let's Encrypt), Bike Log | | free |

**Why a server in Germany and not outside the EU.** Server location doesn't change anything for Strava.
The Strava API agreement is between Strava and you as a developer, wherever the server is. Its
rules, like the 7-day storage limit you accepted as a risk, apply in the same way in Germany or in the
US. Keeping your own data for yourself is "purely personal" use, which GDPR doesn't cover. If it did,
it would apply to you as an EU resident wherever the server is. A server far away only makes every
click slower. So pick the cheapest server close to you.

How it works: two small programs run on the server in Docker. **Bike Log** is the same app as on your
PC, started in "server mode". **Caddy** gets and renews the HTTPS certificate for your domain by
itself. Only ports 22 (SSH), 80 and 443 are open.

---

## What you need to do once (about one hour)

You do steps 1–4 in your web browser. Step 5 means pasting two lines into a terminal window. Write
these down as you go: the **server IP**, your **domain**, the **Google Client ID and secret** and the
**GitHub token**.

### 1. Rent the server (Hetzner)

1. Sign up at **hetzner.com/cloud** and open the **Cloud Console**. Create a project, for example "Bike Log".
2. Click **Add Server** (or "Create Server").
3. **Location**: Nuremberg or Falkenstein (Germany).
4. **Image**: Ubuntu 24.04.
5. **Type**: Shared vCPU, the smallest one that can be ordered. Either x86 (CX…) or Arm (CAX…) works.
6. **Networking**: keep **Public IPv4** switched on. Google and Let's Encrypt need it.
7. **SSH keys**: skip. Hetzner then e-mails you a root password.
8. **Backups**: tick it. It costs a little and saves the whole server every day.
9. Name it `bikelog` and click **Create & Buy now**. After a minute you see the server's **IPv4 address**
   (for example `203.0.113.10`). Note it.

### 2. Domain and DNS

1. Buy a domain at a registrar of your choice, or use one you already have.
2. In the registrar's **DNS** settings, add a record:
   - Type **A**, Name **bikelog** (or `@` to use the bare domain), Value = **the server IPv4 address**, TTL default.
3. Your Bike Log address is then `bikelog.<your domain>`, for example `bikelog.example.com`.
   It can take a few minutes to an hour before the name works everywhere.

### 3. Google sign-in (Google Cloud console)

1. Open **console.cloud.google.com** with your Google account. Accept the terms if it asks.
2. Top left, click the project picker, then **New project**, name "Bike Log", and click **Create**. Make
   sure the new project is selected.
3. Menu → **APIs & Services → OAuth consent screen**. It may now be called **Google Auth Platform**.
   Click **Get started**:
   - App name **Bike Log**, user support e-mail = your Gmail address → Next.
   - Audience: **External** → Next. Contact e-mail = your Gmail address → Next → agree → **Create**.
4. **Audience** (left menu): under **Test users**, click **Add users** and add your Gmail address, plus
   anyone else who should get in. You can leave the app in "Testing". Bike Log only asks Google for
   your e-mail address, so no review by Google is needed.
5. **Clients** (left menu), then **Create client**:
   - Application type **Web application**, name "Bike Log server".
   - **Authorized redirect URIs**, then **Add URI**: `https://bikelog.example.com/auth/callback`. Use your
     own address, starting with https:// and ending in /auth/callback.
   - Click **Create**. Copy the **Client ID** and the **Client secret** right away. Google may not show
     the secret again, so use the download button if it offers one.

### 4. A read-only key for the code (GitHub)

The code repository is private, so the server needs a key that can only read it.

1. On github.com, click your picture (top right), then **Settings → Developer settings → Personal access
   tokens → Fine-grained tokens → Generate new token**.
2. Name "bikelog server". Pick an expiration, such as 1 year, and put a reminder in your calendar.
3. **Repository access**: Only select repositories, then **bike_log**.
4. **Permissions → Repository permissions → Contents: Read-only**. Nothing else.
5. **Generate token**, then copy it. It starts with `github_pat_`.

### 5. Install Bike Log on the server (two lines to paste)

1. On Windows, open **PowerShell** and type `ssh root@203.0.113.10` with your server IP. Answer `yes`
   the first time, then paste the root password from Hetzner's e-mail. Right-click pastes in PowerShell.
   The first login asks you to choose a new password.
2. Paste this, with your token in place of `TOKEN`, and press Enter:

   ```bash
   git clone https://TOKEN@github.com/dirksn74/bike_log.git /opt/bikelog
   ```
3. Then paste this and press Enter:

   ```bash
   bash /opt/bikelog/deploy/install.sh
   ```
   It asks for your **domain**, the **Google Client ID**, the **Google Client secret** (hidden while you
   type) and the **Google e-mail addresses** that may sign in, comma separated. It also asks whether
   Bike Log should **update itself every night**. Say yes, and every change merged into `main` is live
   the next morning. Then it installs everything, which takes about 5–10 minutes.
4. When it says **Done**, open `https://bikelog.<your domain>` in your browser and sign in with Google.

### 6. Bring your data from the PC

1. In the **desktop app** on your PC: **Settings → Backups and export → Back up now**, then click
   **Download** next to the new backup (`bikelog-…-manual.db`).
2. On the **server** (in the browser): **Settings → Backups and export → Bring data from another
   computer**, choose that file and click **Upload backup**. Then click **Restore** next to the uploaded
   backup (`…-uploaded.db`). The empty server database is backed up first.
3. **Strava**: the connection doesn't move with the data, because the key stays in a separate file.
   On strava.com/settings/api, set **Authorization Callback Domain** to your Bike Log domain, for example
   `bikelog.example.com`. Strava always allows `localhost` too, so the desktop app keeps working.
   Then on the server, go to **Settings → Strava**, enter the Client ID and secret, and click
   **Connect with Strava**.
4. From then on, use the server. Avoid entering data in both places, because the two databases don't
   sync with each other.

---

## Everyday use

- **Open**: `https://bikelog.<your domain>` on any device. You stay signed in for 30 days per browser.
  **Settings → Account → Sign out** ends the sign-in on that browser.
- **Updates**: automatic every night at about 04:00 if you said yes. To update right away, connect
  with `ssh root@<ip>` and type `bikelog-update`. Bike Log backs up the database before every update that
  changes the database layout.
- **Backups**: Bike Log keeps a daily backup on the server (Settings → Backups and export, the last 10).
  Hetzner's backups keep the whole server for 7 days. Now and then, click **Download** on a backup to keep
  a copy at home.
- **Restore**: Settings → Backups and export → **Restore** next to a backup, the same as on the PC.

## Changing settings later

Run `bash /opt/bikelog/deploy/install.sh` again. It shows the saved answers. Press Enter to keep each
one, or type a new value. Use it to add a Google account to the allowed list or switch nightly updates
on or off. A Google account must also be a **Test user** in the Google console as long as the app is in
"Testing".

- **Sign everybody out** (for example after losing a phone): delete the signing key and restart:
  `docker compose -f /opt/bikelog/deploy/compose.yml exec bikelog rm /data/session.key` and then
  `docker compose -f /opt/bikelog/deploy/compose.yml restart bikelog`.
- **GitHub token expired** (nightly update log says "Authentication failed"): make a new token (step 4)
  and run `git -C /opt/bikelog remote set-url origin https://NEWTOKEN@github.com/dirksn74/bike_log.git`.
- **See what the app is doing**: Settings → Diagnostics (log), or on the server
  `docker compose -f /opt/bikelog/deploy/compose.yml logs --tail 100`.
- **Update log**: `journalctl -u bikelog-update --since yesterday`.

## When something is wrong

| You see | Why / what to do |
|---|---|
| Browser: "can't reach this page" | DNS not there yet (wait up to an hour), or the A record has a typo. |
| Browser: certificate warning right after install | Caddy is still getting the certificate; wait a minute and reload. DNS must point to the server first. |
| Google: "redirect_uri_mismatch" | The redirect URI in the Google client (step 3.5) must be exactly `https://<your domain>/auth/callback`. |
| Google: "Access blocked … has not completed the Google verification process" | Add the account as a Test user (step 3.4). |
| Bike Log: "Not allowed" | That Google account isn't in the allowed list; run install.sh again and add it. |
| Strava: "redirect_uri invalid" | Set Strava's Authorization Callback Domain to your Bike Log domain (step 6.3). |

## For developers: what server mode is

- `python -m bikelog --server` (or `BIKELOG_SERVER=1`) with settings from the environment
  (`env.example`): `BIKELOG_PUBLIC_URL`, `BIKELOG_GOOGLE_CLIENT_ID`, `BIKELOG_GOOGLE_CLIENT_SECRET`,
  `BIKELOG_ALLOWED_EMAILS`, optional `BIKELOG_SESSION_SECRET` (otherwise `session.key` in the data folder),
  `BIKELOG_SESSION_DAYS`, `BIKELOG_HOST` (0.0.0.0 in the container), `BIKELOG_PORT`.
- Sign-in: `backend/bikelog/server_auth.py` (OpenID Connect code flow against Google, state + nonce in a
  short-lived signed cookie, the ID token checked for issuer, audience, expiry, nonce, verified e-mail and
  allowlist; HMAC-signed session cookie, HttpOnly + Secure + SameSite=Lax). Every request needs the session
  except `/auth/*` and `/api/health` (which only answers `{"ok": true}` when signed out). Mutations also
  need the CSRF header `X-BikeLog-Token` (derived from the session) and a matching `Origin` if sent.
- Single user. It's still one database, not the multi-user design from the 2026-10-26 hosting
  assessment. Everyone on the allowlist sees and edits the same data.
- Files: `Dockerfile` (screens built with Node, app on python:3.12-slim, non-root), `compose.yml`
  (bikelog + caddy, data in the volume `bikelog-data`), `Caddyfile`, `install.sh`, `update.sh`.
