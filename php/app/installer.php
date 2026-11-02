<?php
declare(strict_types=1);

// First-time setup: create the tables and the first admin account. Guarded by the install key from
// config.php, and refuses to run once any account exists.

final class Installer
{
    private static ?bool $installed = null;

    public static function isInstalled(): bool
    {
        if (self::$installed === null) {
            try {
                self::$installed = (int)Db::value("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'") > 0;
            } catch (PDOException) {
                self::$installed = false;
            }
        }
        return self::$installed;
    }

    public static function reset(): void
    {
        self::$installed = null;
    }

    public static function install(string $key, string $email, string $name, string $password): int
    {
        $expected = (string)Config::get('install_key', '');
        if (strlen($expected) < 16) {
            throw new UserError('Set install_key in config/config.php (at least 16 characters) first.');
        }
        if (!RateLimit::allowedSafe('install', Request::ip(), 10, 3600)) {
            throw new UserError('Too many attempts. Wait an hour.');
        }
        if (!hash_equals($expected, $key)) {
            RateLimit::hitSafe('install', Request::ip());
            throw new UserError('The install key is wrong.');
        }
        Migrator::migrate();
        if (self::isInstalledFresh()) {
            throw new UserError('Bike Log is already installed.');
        }
        $email = Auth::normalizeEmail($email);
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            throw new UserError('Please enter a valid email address.');
        }
        if (trim($name) === '') {
            throw new UserError('Please enter your name.');
        }
        Auth::validatePassword($password, $email);
        $now = now_utc();
        $id = Db::insert('users', ['email' => $email, 'display_name' => trim($name), 'password_hash' => Auth::hash($password),
            'role' => 'ADMIN', 'status' => 'ACTIVE', 'email_verified_at' => $now,
            'timezone' => Config::get('default_timezone', 'Europe/Berlin'), 'created_at' => $now, 'updated_at' => $now]);
        Domain::seedUser($id);
        Audit::log('installed', $id, 'first admin', $id);
        self::$installed = true;
        return $id;
    }

    private static function isInstalledFresh(): bool
    {
        self::$installed = null;
        return (int)Db::value('SELECT COUNT(*) FROM users') > 0;
    }
}
