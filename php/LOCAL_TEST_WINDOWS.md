# Try the web version on your Windows PC (XAMPP)

This runs the PHP web version of Bike Log on your own PC, only for you, so you can click through it before
it goes on a real web server. Nothing leaves your PC. Emails (password reset, invitations) are not sent:
they are written to a text file instead.

It takes about 20 minutes the first time. After that, starting it is one double-click (step 9).

Your Bike Log folder is `D:\Ablage\Coding\bike_log` below. If yours is somewhere else, use your path.

## 1. Install XAMPP (once)

1. Download XAMPP for Windows from https://www.apachefriends.org (the newest version, PHP 8.1 or newer).
2. Run the installer. Keep the default folder `C:\xampp`. Of the components, you need **MySQL**,
   **PHP** and **phpMyAdmin** (Apache comes with phpMyAdmin; keep it ticked).
3. If Windows asks whether to allow Apache or MySQL through the firewall, choose **private networks only**.

## 2. Start MySQL (every time)

1. Open the **XAMPP Control Panel** (Start menu → XAMPP).
2. Press **Start** next to **Apache** and next to **MySQL**. Both names turn green.
   - Apache is only needed for phpMyAdmin (step 4). Bike Log itself does not use it.
   - If MySQL does not turn green, another MySQL already uses port 3306 on your PC. Stop that one first,
     or ask me.

## 3. Get the newest code (Git, in PowerShell)

The web version is in the `main` branch. Open **PowerShell** and type these lines one by one (press Enter
after each):

```
cd D:\Ablage\Coding\bike_log
git status
```

`git status` must say **nothing to commit, working tree clean**. If it lists changed files, stop here and
send me what it shows (so nothing of yours gets lost).

```
git fetch origin
git checkout main
git pull
```

`git checkout main` switches the folder to the `main` branch; `git pull` downloads the newest version.
You now have a `php` folder in `D:\Ablage\Coding\bike_log`.

Good to know: `main` also has the newest desktop app, so `packaging\build.ps1` works from here as before.
Next time you only need `git pull` (in the same folder) to get updates.

## 4. Create the database (once, in phpMyAdmin)

1. In the browser open **http://localhost/phpmyadmin**.
2. On the left click **New**.
3. Database name: `bikelog`. In the box next to it choose **utf8mb4_unicode_ci**.
4. Press **Create**. The database is empty; Bike Log fills it in step 7.

## 5. Make the settings file (once)

1. In Windows Explorer open `D:\Ablage\Coding\bike_log\php\config`.
2. Copy `config.local-sample.php` and rename the copy to `config.php`.
   (If Windows hides file endings, the names show as `config.local-sample` and `config`; that is fine.)

That is all: the file is already set for XAMPP (user `root`, no password, emails to a file). You do not
need to change anything in it. `config.php` is never uploaded to GitHub.

## 6. Start Bike Log

Double-click `D:\Ablage\Coding\bike_log\php\start-local.bat`.

A black window opens and, after two seconds, your browser shows **http://127.0.0.1:8080/**.
Keep the black window open while you use Bike Log; closing it stops Bike Log.

If Windows shows "Windows protected your PC", click **More info** → **Run anyway** (the file only starts
XAMPP's PHP; you can open it in Notepad to see what it does).

## 7. Create your admin account (once)

The first page is **Install Bike Log**:

- **Install key:** `local-test-install-key-2026` (it is in `config.php`).
- Your name, your email address, and a password (at least 10 characters).

Press **Install**. Bike Log creates its tables in the `bikelog` database and signs you in as admin.

## 8. Try it

- Add a bike, parts, rides; log maintenance; look at the reminders.
- **Admin** (top bar) shows users, audit log, site settings and system.
- To test another user: sign out, then **Create an account** on the sign-in page (shown when **Admin →
  Site settings** allows sign-up), or invite someone in **Admin → Users**.
- **Emails:** sign-up confirmations, invitations and password-reset links are written to
  `D:\Ablage\Coding\bike_log\php\storage\mail.log`. Open it with Notepad, scroll to the end and copy the
  link into the browser. Example: sign out → **Forgot your password?** → your email → open `mail.log` →
  copy the `http://127.0.0.1:8080/index.php?r=reset&t=...` link.
- **Admin → System → Send test email** also writes into `mail.log`.

## 9. Next time

1. XAMPP Control Panel → **Start** MySQL (Apache only if you want phpMyAdmin).
2. Double-click `php\start-local.bat`.

To get my newest changes first: PowerShell → `cd D:\Ablage\Coding\bike_log` → `git pull`. If an update
changes the database, Bike Log shows a yellow bar for admins ("The database needs an update"): click **Update now**.

## Starting over

To throw your test data away: phpMyAdmin → click `bikelog` on the left → **Operations** → **Drop the
database**, then create it again (step 4) and open Bike Log (step 6): it shows the setup page again.

## If something goes wrong

| What you see | What to do |
|---|---|
| Black window says "PHP from XAMPP was not found" | XAMPP is not in `C:\xampp`. Open `start-local.bat` in Notepad and change the `PHP=` line to your `xampp\php\php.exe`. |
| Black window says "config\config.php is missing" | Do step 5. |
| Browser: "Something went wrong" or a database error | MySQL is not started (step 2) or the `bikelog` database is missing (step 4). |
| Black window says the address is already in use | Something else uses port 8080. Open `start-local.bat` in Notepad, change `PORT=8080` to `8081`, and in `config.php` change `base_url` to `http://127.0.0.1:8081`. |
| The page does not open by itself | Open http://127.0.0.1:8080/ in the browser yourself. |
| Any error text | `D:\Ablage\Coding\bike_log\php\storage\php-error.log` has the details; send me the last lines. |

This local setup is only for testing. For the real web server use the steps in [README.md](README.md)
("Install on shared hosting"): there you need HTTPS, a real password and real email (SMTP) settings.
