# Installing Bike Log (for friends)

Bike Log keeps track of your road bikes: rides, km per part, maintenance, wear and what needs attention
next. It runs **on your own Windows PC**. There is no account and no cloud: your data never leaves your PC
(only if you connect Strava, Bike Log talks to Strava to fetch your rides).

Needs: Windows 10 or 11 (64-bit). No admin rights, no Python, nothing else.

## Install

1. Download `BikeLog-<version>-setup.exe` from the release page (under **Assets**).
2. Double-click it. Windows will probably warn you, because the app is not signed by a company:
   * Browser says "not commonly downloaded": choose **Keep** (in Edge: `…` → Keep → Show more → Keep anyway).
   * Blue window "Windows protected your PC": click **More info**, then **Run anyway**.
3. Click through the setup. It installs only for you, into `%LOCALAPPDATA%\Programs\BikeLog`.
4. Bike Log starts and opens in your browser at `http://127.0.0.1:8765/`. Next time, start it from the
   Start menu ("Bike Log"). A small black window opens alongside: it shows the address, and closing it
   stops Bike Log. Leave it open (minimised) while you use the app.

The first start shows **two sample bikes** so you can look around. When you are ready for your own bikes:
**Settings → Fresh start**, type `RESET`, press **Reset database**.

## Your data

* Everything is stored in `%LOCALAPPDATA%\BikeLog` (database, automatic backups, logs). Paste that into
  the Explorer address bar to find it.
* **Settings → Backups and export** makes a backup or a full export (zip). Copy one to a USB stick or
  your cloud drive now and then.
* Uninstalling removes the program but **keeps** your data folder. Delete it yourself if you really want
  everything gone.

## Updating

Download the newer `BikeLog-<version>-setup.exe` and run it, just like the first time. Close Bike Log
first (the setup offers to do it). Your bikes, rides and history stay: the update replaces only the
program, and if the new version changes how data is stored, Bike Log writes a backup first
(`pre-upgrade`) and then upgrades the database. You can skip versions. Settings shows which version runs.

## Strava (optional)

Bike Log works fine without Strava (enter rides yourself, or import Strava's `activities.csv` export).
To fetch rides automatically, you need **your own** Strava API app (Strava allows each new app only
for the one person who made it, so you cannot use someone else's):

1. Go to <https://www.strava.com/settings/api> and create an app. Name and website can be anything
   (e.g. "My Bike Log", `http://localhost`). Set **Authorization Callback Domain** to `localhost`.
2. In Bike Log: **Settings → Strava**, enter the **Client ID** and **Client Secret** from that page,
   press **Save app details**. They are stored only on your PC.
3. Press **Connect with Strava**, then **Authorize** on Strava. Then **Sync now**.

Bikes are matched by their Strava gear name; a bike that Bike Log does not know yet is created (or switch
on "Import only rides with known bikes"). **Disconnect** stops syncing; your rides stay.

## Something wrong?

Settings → **Diagnostics** shows the version and recent changes; logs are in `%LOCALAPPDATA%\BikeLog\logs`.
Send the version number and what you did to the person who gave you the app.
