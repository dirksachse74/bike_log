<?php
declare(strict_types=1);

// Accounts: sign-up, sign-in, email verification, password reset, invitations.
// Rules: passwords hashed with password_hash (Argon2id when available, else bcrypt); sign-in and reset
// answers never reveal whether an email address has an account; one-time links are random 256-bit
// tokens stored only as SHA-256, single use, short lived; a password change logs out all other sessions.

final class Auth
{
    public const MIN_PASSWORD = 10;
    public const VERIFY_TTL = 86400 * 2;   // 48 h
    public const RESET_TTL = 3600;          // 1 h
    public const INVITE_TTL = 86400 * 7;    // 7 days
    private static ?array $user = null;
    private static bool $loaded = false;

    public static function algo(): string|int|null
    {
        return defined('PASSWORD_ARGON2ID') ? PASSWORD_ARGON2ID : PASSWORD_BCRYPT;
    }

    public static function hash(string $password): string
    {
        return password_hash($password, self::algo());
    }

    /** A real hash of a random string, so unknown emails cost the same time as known ones. */
    private static function dummyHash(): string
    {
        $h = Settings::get('dummy_hash');
        if ($h === '' || password_needs_rehash($h, self::algo())) {
            $h = self::hash(bin2hex(random_bytes(16)));
            Settings::set('dummy_hash', $h);   // stored once, so later checks cost one verify only
        }
        return $h;
    }

    public static function user(): ?array
    {
        if (!self::$loaded) {
            self::$loaded = true;
            $id = (int)($_SESSION['uid'] ?? 0);
            if ($id > 0) {
                $u = Db::one('SELECT * FROM users WHERE id = ?', [$id]);
                // a password change, block or "log out everywhere" raises session_version
                if ($u && $u['status'] === 'ACTIVE' && (int)$u['session_version'] === (int)($_SESSION['sv'] ?? -1)) {
                    self::$user = $u;
                } else {
                    self::logoutLocal();
                }
            }
        }
        return self::$user;
    }

    public static function id(): int
    {
        return (int)(self::user()['id'] ?? 0);
    }

    public static function isAdmin(): bool
    {
        return (self::user()['role'] ?? '') === 'ADMIN';
    }

    public static function forget(): void
    {
        self::$user = null;
        self::$loaded = false;
    }

    public static function normalizeEmail(string $email): string
    {
        return mb_strtolower(trim($email));
    }

    public static function validatePassword(string $pw, string $email = ''): void
    {
        if (mb_strlen($pw) < self::MIN_PASSWORD) {
            throw new UserError(t('The password needs at least {n} characters.', ['n' => self::MIN_PASSWORD]));
        }
        if (strlen($pw) > 1024) {
            throw new UserError(t('The password is too long.'));
        }
        if ($email !== '' && mb_strtolower($pw) === mb_strtolower($email)) {
            throw new UserError(t('The password must not be your email address.'));
        }
        $common = ['password123', '1234567890', 'qwertyuiop', 'passwort123', 'letmein1234', 'bikelog123'];
        if (in_array(mb_strtolower($pw), $common, true)) {
            throw new UserError(t('That password is too common.'));
        }
    }

    // ---------------------------------------------------------------- sign in / out

    /** Returns the user row or throws UserError with a message that never tells whether the email exists. */
    public static function attempt(string $email, string $password): array
    {
        $email = self::normalizeEmail($email);
        $ip = Request::ip();
        if (!RateLimit::allowed('login-email', $email, 5, 900) || !RateLimit::allowed('login-ip', $ip, 30, 900)) {
            Audit::log('login_throttled', null, $email);
            throw new UserError(t('Too many sign-in attempts. Please wait 15 minutes and try again.'));
        }
        $u = Db::one('SELECT * FROM users WHERE email = ?', [$email]);
        // same work whether or not the account exists (no timing hint)
        $hash = $u['password_hash'] ?? self::dummyHash();
        $ok = password_verify($password, $hash) && $u !== null;
        if (!$ok) {
            RateLimit::hit('login-email', $email);
            RateLimit::hit('login-ip', $ip);
            Audit::log('login_failed', $u['id'] ?? null, $email, 0);
            throw new UserError(t('Email or password is wrong.'));
        }
        if ($u['status'] !== 'ACTIVE') {
            Audit::log('login_blocked', (int)$u['id'], null, 0);
            throw new UserError(t('This account is blocked. Please contact the site admin.'));
        }
        if (Settings::get('require_verification') === '1' && $u['email_verified_at'] === null) {
            throw new UserError(t('Please confirm your email address first. We can send the link again below.'));
        }
        if (Settings::get('maintenance_mode') === '1' && $u['role'] !== 'ADMIN') {
            throw new UserError(t('The site is in maintenance mode. Please try again later.'));
        }
        if (password_needs_rehash($u['password_hash'], self::algo())) {
            Db::run('UPDATE users SET password_hash = ? WHERE id = ?', [self::hash($password), $u['id']]);
        }
        RateLimit::clear('login-email', $email);
        self::login($u);
        return $u;
    }

    public static function login(array $u): void
    {
        session_regenerate_id(true);           // no session fixation
        $_SESSION['uid'] = (int)$u['id'];
        $_SESSION['sv'] = (int)$u['session_version'];
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
        Db::run('UPDATE users SET last_login_at = ? WHERE id = ?', [now_utc(), $u['id']]);
        self::forget();
        Audit::log('login', (int)$u['id'], null, (int)$u['id']);
    }

    public static function logoutLocal(): void
    {
        $_SESSION = [];
        if (session_status() === PHP_SESSION_ACTIVE) {
            session_regenerate_id(true);
        }
        self::$user = null;
    }

    /** Ends every session of this user (other browsers too). */
    public static function bumpSessions(int $userId): void
    {
        Db::run('UPDATE users SET session_version = session_version + 1, updated_at = ? WHERE id = ?', [now_utc(), $userId]);
    }

    // ---------------------------------------------------------------- sign up

    public static function registrationOpen(): bool
    {
        return Settings::get('registration') === 'open';
    }

    public static function emailDomainAllowed(string $email): bool
    {
        $allowed = array_filter(array_map(fn($d) => mb_strtolower(trim($d)), explode(',', Settings::get('allowed_email_domains'))));
        if (!$allowed) {
            return true;
        }
        $domain = substr(strrchr($email, '@') ?: '', 1);
        return in_array($domain, $allowed, true);
    }

    /**
     * Create an account. If the email is taken, the owner gets a "someone tried to sign up" email and the
     * caller shows the same answer as for a new account, so the form cannot be used to test addresses.
     * Returns the new user id, or null when the address already had an account.
     */
    public static function register(string $email, string $name, string $password, ?array $invite = null): ?int
    {
        $email = self::normalizeEmail($email);
        if (!filter_var($email, FILTER_VALIDATE_EMAIL) || strlen($email) > 190) {
            throw new UserError(t('Please enter a valid email address.'));
        }
        $name = trim($name);
        if ($name === '' || mb_strlen($name) > 100) {
            throw new UserError(t('Please enter your name (up to 100 characters).'));
        }
        self::validatePassword($password, $email);
        if ($invite === null && !self::emailDomainAllowed($email)) {
            throw new UserError(t('Sign-up is limited to certain email domains on this site.'));
        }
        $existing = Db::one('SELECT id FROM users WHERE email = ?', [$email]);
        if ($existing) {
            Mailer::send($email, t('Someone tried to sign up with your email'),
                t("Hello,\n\nsomeone tried to create a Bike Log account with this email address, but you already have one.\nIf it was you, sign in here: {login}\nForgot the password? {forgot}\n\nIf it was not you, you can ignore this email.\n",
                ['login' => abs_url('login'), 'forgot' => abs_url('forgot')]));
            Audit::log('register_existing', (int)$existing['id'], null, 0);
            return null;
        }
        $now = now_utc();
        $verified = ($invite !== null && $invite['email'] === $email) ? $now : null;
        $id = Db::insert('users', [
            'email' => $email, 'display_name' => $name, 'password_hash' => self::hash($password),
            'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $verified,
            'timezone' => Config::get('default_timezone', 'Europe/Berlin'), 'lang' => I18n::lang(), 'created_at' => $now, 'updated_at' => $now,
        ]);
        Domain::seedUser($id);
        Audit::log('register', $id, $invite ? 'invited' : null, $id);
        if ($verified === null && Settings::get('require_verification') === '1') {
            self::sendVerification($id, $email);
        }
        return $id;
    }

    // ---------------------------------------------------------------- tokens

    public static function createToken(?int $userId, string $purpose, int $ttl, ?string $email = null): string
    {
        $token = bin2hex(random_bytes(32));
        Db::insert('user_tokens', [
            'user_id' => $userId, 'purpose' => $purpose, 'token_hash' => hash('sha256', $token), 'email' => $email,
            'created_by' => self::id() ?: null, 'created_at' => now_utc(), 'expires_at' => gmdate('Y-m-d H:i:s', time() + $ttl),
        ]);
        return $token;
    }

    /** A valid (unused, unexpired) token row, or null. */
    public static function findToken(string $token, string $purpose): ?array
    {
        if (!preg_match('/^[0-9a-f]{64}$/', $token)) {
            return null;
        }
        return Db::one('SELECT * FROM user_tokens WHERE token_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?',
            [hash('sha256', $token), $purpose, now_utc()]);
    }

    /** Mark used; returns false if someone else used it a moment earlier (single use, race safe). */
    public static function consumeToken(int $tokenId): bool
    {
        return Db::run('UPDATE user_tokens SET used_at = ? WHERE id = ? AND used_at IS NULL', [now_utc(), $tokenId])->rowCount() === 1;
    }

    public static function sendVerification(int $userId, string $email): void
    {
        Db::run("UPDATE user_tokens SET used_at = ? WHERE user_id = ? AND purpose = 'VERIFY' AND used_at IS NULL", [now_utc(), $userId]);
        $t = self::createToken($userId, 'VERIFY', self::VERIFY_TTL);
        Mailer::send($email, t('Confirm your email for {site}', ['site' => Settings::get('site_name')]),
            t("Hello,\n\nplease confirm your email address to finish setting up your account:\n\n{link}\n\nThe link works once and expires in 48 hours.\nIf you did not sign up, ignore this email.\n",
            ['link' => abs_url('verify', ['t' => $t])]));
    }

    public static function verify(string $token): bool
    {
        $row = self::findToken($token, 'VERIFY');
        if (!$row || !self::consumeToken((int)$row['id'])) {
            return false;
        }
        Db::run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?', [now_utc(), now_utc(), $row['user_id']]);
        Audit::log('email_verified', (int)$row['user_id'], null, (int)$row['user_id']);
        return true;
    }

    /** Always behaves the same for the caller, whether or not the address has an account. */
    public static function requestReset(string $email): void
    {
        $email = self::normalizeEmail($email);
        $ip = Request::ip();
        if (!RateLimit::allowed('reset-ip', $ip, 10, 3600) || !RateLimit::allowed('reset-email', $email, 3, 3600)) {
            Audit::log('reset_throttled', null, $email, 0);
            return;   // silently: no hint either way
        }
        RateLimit::hit('reset-ip', $ip);
        RateLimit::hit('reset-email', $email);
        $u = Db::one('SELECT id, email, status FROM users WHERE email = ?', [$email]);
        if (!$u || $u['status'] !== 'ACTIVE') {
            Audit::log('reset_unknown', null, $email, 0);
            return;
        }
        self::sendReset((int)$u['id'], $u['email']);
        Audit::log('reset_requested', (int)$u['id'], null, 0);
    }

    public static function sendReset(int $userId, string $email): void
    {
        // only the newest link works
        Db::run("UPDATE user_tokens SET used_at = ? WHERE user_id = ? AND purpose = 'RESET' AND used_at IS NULL", [now_utc(), $userId]);
        $t = self::createToken($userId, 'RESET', self::RESET_TTL);
        Mailer::send($email, t('Reset your {site} password', ['site' => Settings::get('site_name')]),
            t("Hello,\n\nsomeone (hopefully you) asked to reset the password for this account.\nChoose a new password here:\n\n{link}\n\nThe link works once and expires in 1 hour. If you did not ask for it, ignore this email; your password stays the same.\n",
            ['link' => abs_url('reset', ['t' => $t])]));
    }

    public static function resetPassword(string $token, string $password): void
    {
        $row = self::findToken($token, 'RESET');
        if (!$row) {
            throw new UserError(t('This reset link is invalid or has expired. Please ask for a new one.'));
        }
        $u = Db::one('SELECT * FROM users WHERE id = ?', [$row['user_id']]);
        self::validatePassword($password, $u['email']);
        if (!self::consumeToken((int)$row['id'])) {
            throw new UserError(t('This reset link was already used.'));
        }
        Db::run('UPDATE users SET password_hash = ?, session_version = session_version + 1, email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?',
            [self::hash($password), now_utc(), now_utc(), $u['id']]);
        RateLimit::clear('login-email', $u['email']);
        Audit::log('password_reset', (int)$u['id'], null, (int)$u['id']);
        Mailer::send($u['email'], t('Your password was changed'),
            t("Hello,\n\nthe password of your {site} account was just changed.\nIf this was not you, reset it now: {link} and tell the site admin.\n",
            ['site' => Settings::get('site_name'), 'link' => abs_url('forgot')]));
    }

    public static function changePassword(int $userId, string $current, string $new): void
    {
        $u = Db::one('SELECT * FROM users WHERE id = ?', [$userId]);
        if (!RateLimit::allowed('pwchange', (string)$userId, 5, 900)) {
            throw new UserError(t('Too many attempts. Please wait 15 minutes.'));
        }
        if (!password_verify($current, $u['password_hash'])) {
            RateLimit::hit('pwchange', (string)$userId);
            throw new UserError(t('Your current password is wrong.'));
        }
        self::validatePassword($new, $u['email']);
        Db::run('UPDATE users SET password_hash = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?',
            [self::hash($new), now_utc(), $userId]);
        Audit::log('password_changed', $userId);
        // keep this browser signed in
        $_SESSION['sv'] = (int)$u['session_version'] + 1;
        session_regenerate_id(true);
        self::forget();
    }

    public static function invite(string $email): void
    {
        $email = self::normalizeEmail($email);
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            throw new UserError(t('Please enter a valid email address.'));
        }
        if (Db::one('SELECT id FROM users WHERE email = ?', [$email])) {
            throw new UserError(t('This address already has an account.'));
        }
        $t = self::createToken(null, 'INVITE', self::INVITE_TTL, $email);
        Mailer::send($email, t('You are invited to {site}', ['site' => Settings::get('site_name')]),
            t("Hello,\n\n{who} invited you to {site}, a log for your bikes, parts, rides and maintenance.\n\nCreate your account here:\n\n{link}\n\nThe link works once and expires in 7 days.\n",
            ['who' => self::user()['display_name'] ?? t('The admin'), 'site' => Settings::get('site_name'), 'link' => abs_url('register', ['invite' => $t])]));
        Audit::log('invite_sent', null, $email);
    }
}
