<?php
declare(strict_types=1);

// Core plumbing: configuration, database, escaping, sessions, CSRF, flash messages, audit log,
// rate limiting and site settings. No framework, no Composer packages: it runs on plain shared hosting.

const BIKELOG_PHP_VERSION = '0.1.0';

final class Config
{
    private static ?array $cfg = null;

    public static function load(): array
    {
        if (self::$cfg === null) {
            $path = getenv('BIKELOG_CONFIG') ?: __DIR__ . '/../config/config.php';
            if (!is_file($path)) {
                throw new RuntimeException('config/config.php is missing. Copy config/config.sample.php to config/config.php and fill it in.');
            }
            self::$cfg = require $path;
        }
        return self::$cfg;
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        $cur = self::load();
        foreach (explode('.', $key) as $part) {
            if (!is_array($cur) || !array_key_exists($part, $cur)) {
                return $default;
            }
            $cur = $cur[$part];
        }
        return $cur;
    }
}

final class Db
{
    private static ?PDO $pdo = null;

    public static function pdo(): PDO
    {
        if (self::$pdo === null) {
            $c = Config::get('db');
            $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4', $c['host'], (int)($c['port'] ?? 3306), $c['name']);
            self::$pdo = new PDO($dsn, $c['user'], $c['pass'], [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,     // real prepared statements
                PDO::ATTR_STRINGIFY_FETCHES => false,
            ]);
            self::$pdo->exec("SET time_zone = '+00:00', sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ENGINE_SUBSTITUTION'");
        }
        return self::$pdo;
    }

    /** Run a prepared statement. Values are always bound, never pasted into SQL. */
    public static function run(string $sql, array $params = []): PDOStatement
    {
        $st = self::pdo()->prepare($sql);
        $st->execute($params);
        return $st;
    }

    public static function one(string $sql, array $params = []): ?array
    {
        $row = self::run($sql, $params)->fetch();
        return $row === false ? null : $row;
    }

    public static function all(string $sql, array $params = []): array
    {
        return self::run($sql, $params)->fetchAll();
    }

    public static function value(string $sql, array $params = []): mixed
    {
        $v = self::run($sql, $params)->fetchColumn();
        return $v === false ? null : $v;
    }

    public static function insert(string $table, array $row): int
    {
        $cols = array_keys($row);
        foreach ($cols as $c) {
            if (!preg_match('/^[a-z_]+$/', $c)) {
                throw new InvalidArgumentException('bad column');
            }
        }
        $sql = sprintf('INSERT INTO %s (%s) VALUES (%s)', $table, implode(',', $cols),
            implode(',', array_fill(0, count($cols), '?')));
        self::run($sql, array_values($row));
        return (int)self::pdo()->lastInsertId();
    }

    /** UPDATE ... WHERE id = ? AND user_id = ? (owner check built in). */
    public static function updateOwned(string $table, int $id, int $userId, array $row): int
    {
        $sets = [];
        foreach (array_keys($row) as $c) {
            if (!preg_match('/^[a-z_]+$/', $c)) {
                throw new InvalidArgumentException('bad column');
            }
            $sets[] = "$c = ?";
        }
        $params = array_values($row);
        $params[] = $id;
        $params[] = $userId;
        return self::run(sprintf('UPDATE %s SET %s WHERE id = ? AND user_id = ?', $table, implode(', ', $sets)), $params)->rowCount();
    }

    public static function tx(callable $fn): mixed
    {
        $pdo = self::pdo();
        if ($pdo->inTransaction()) {
            return $fn();   // nested: the outer transaction commits or rolls back
        }
        $pdo->beginTransaction();
        try {
            $r = $fn();
            $pdo->commit();
            return $r;
        } catch (Throwable $e) {
            $pdo->rollBack();
            throw $e;
        }
    }

    public static function reset(): void
    {
        self::$pdo = null;
    }
}

// ------------------------------------------------------------------ small helpers

function h(mixed $s): string
{
    return htmlspecialchars((string)($s ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function url(string $route = 'home', array $params = []): string
{
    $q = array_merge(['r' => $route], $params);
    if ($route === 'home') {
        unset($q['r']);
    }
    return 'index.php' . ($q ? '?' . http_build_query($q) : '');
}

function abs_url(string $route, array $params = []): string
{
    return rtrim((string)Config::get('base_url'), '/') . '/' . url($route, $params);
}

function redirect(string $route = 'home', array $params = []): never
{
    header('Location: ' . url($route, $params), true, 303);
    exit;
}

function now_utc(): string
{
    return gmdate('Y-m-d H:i:s');
}

function user_tz(): DateTimeZone
{
    $u = Auth::user();
    $tz = $u['timezone'] ?? Config::get('default_timezone', 'Europe/Berlin');
    try {
        return new DateTimeZone($tz);
    } catch (Throwable) {
        return new DateTimeZone('UTC');
    }
}

function today(): string
{
    return (new DateTimeImmutable('now', user_tz()))->format('Y-m-d');
}

/** Show a UTC timestamp in the signed-in user's time zone. */
function local_time(?string $utc): string
{
    if (!$utc) {
        return '';
    }
    $d = new DateTimeImmutable($utc, new DateTimeZone('UTC'));
    return $d->setTimezone(user_tz())->format('Y-m-d H:i');
}

function post(string $key, string $default = ''): string
{
    $v = $_POST[$key] ?? $default;
    return is_string($v) ? trim($v) : $default;
}

function get_param(string $key, string $default = ''): string
{
    $v = $_GET[$key] ?? $default;
    return is_string($v) ? trim($v) : $default;
}

function get_int(string $key): int
{
    $v = $_GET[$key] ?? $_POST[$key] ?? '';
    return is_string($v) && ctype_digit($v) ? (int)$v : 0;
}

function nullable(string $s): ?string
{
    return $s === '' ? null : $s;
}

/** A date typed into a form (YYYY-MM-DD) or null. Throws on nonsense. */
function parse_date(string $s, bool $required = false): ?string
{
    if ($s === '') {
        if ($required) {
            throw new UserError('Please enter a date.');
        }
        return null;
    }
    $d = DateTimeImmutable::createFromFormat('!Y-m-d', $s);
    if (!$d || $d->format('Y-m-d') !== $s) {
        throw new UserError("'$s' is not a valid date (use YYYY-MM-DD).");
    }
    return $s;
}

function parse_number(string $s, string $label, bool $allowNegative = false): ?float
{
    if ($s === '') {
        return null;
    }
    $s = str_replace(',', '.', $s);
    if (!is_numeric($s)) {
        throw new UserError("$label must be a number.");
    }
    $f = (float)$s;
    if (!$allowNegative && $f < 0) {
        throw new UserError("$label cannot be negative.");
    }
    return $f;
}

function parse_money_cents(string $s, string $label = 'Price'): ?int
{
    $f = parse_number($s, $label);
    return $f === null ? null : (int)round($f * 100);
}

function money(?int $cents): string
{
    return $cents === null ? '' : number_format($cents / 100, 2, '.', ' ');
}

function km(?float $v, int $dec = 0): string
{
    return $v === null ? '–' : number_format($v, $dec, '.', ' ') . ' km';
}

function duration(?int $s): string
{
    if ($s === null) {
        return '–';
    }
    return sprintf('%d:%02d h', intdiv($s, 3600), intdiv($s % 3600, 60));
}

/** Parse "1:30", "1:30:00" or "90" (minutes) into seconds. */
function parse_duration(string $s): ?int
{
    if ($s === '') {
        return null;
    }
    if (preg_match('/^(\d+):(\d{1,2})(?::(\d{1,2}))?$/', $s, $m)) {
        return (int)$m[1] * 3600 + (int)$m[2] * 60 + (int)($m[3] ?? 0);
    }
    if (ctype_digit($s)) {
        return (int)$s * 60;
    }
    throw new UserError('Duration: use h:mm (for example 2:15) or minutes.');
}

final class UserError extends RuntimeException
{
}

final class NotFound extends RuntimeException
{
}

// ------------------------------------------------------------------ request info

final class Request
{
    public static function ip(): string
    {
        $ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
        if (Config::get('trust_proxy_headers') && !empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
            $first = trim(explode(',', (string)$_SERVER['HTTP_X_FORWARDED_FOR'])[0]);
            if (filter_var($first, FILTER_VALIDATE_IP)) {
                $ip = $first;
            }
        }
        return $ip;
    }

    public static function isHttps(): bool
    {
        if (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') {
            return true;
        }
        return Config::get('trust_proxy_headers') && ($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https';
    }

    public static function isPost(): bool
    {
        return ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST';
    }
}

// ------------------------------------------------------------------ session, CSRF, flash

final class Session
{
    public static function start(): void
    {
        if (session_status() === PHP_SESSION_ACTIVE) {
            return;
        }
        ini_set('session.use_strict_mode', '1');
        ini_set('session.use_only_cookies', '1');
        ini_set('session.use_trans_sid', '0');
        ini_set('session.gc_maxlifetime', '43200');
        session_name('bikelog_sid');
        session_set_cookie_params([
            'lifetime' => 0,
            'path' => '/',
            'secure' => Request::isHttps() || (bool)Config::get('force_https', true),
            'httponly' => true,
            'samesite' => 'Lax',
        ]);
        session_start();
        // idle timeout: 12 hours without a request ends the session
        $now = time();
        if (isset($_SESSION['seen']) && $now - (int)$_SESSION['seen'] > 43200) {
            $_SESSION = [];
            session_regenerate_id(true);
        }
        $_SESSION['seen'] = $now;
    }

    public static function flash(string $type, string $msg): void
    {
        $_SESSION['flash'][] = [$type, $msg];
    }

    public static function takeFlash(): array
    {
        $f = $_SESSION['flash'] ?? [];
        unset($_SESSION['flash']);
        return $f;
    }
}

final class Csrf
{
    public static function token(): string
    {
        if (empty($_SESSION['csrf'])) {
            $_SESSION['csrf'] = bin2hex(random_bytes(32));
        }
        return $_SESSION['csrf'];
    }

    public static function field(): string
    {
        return '<input type="hidden" name="_csrf" value="' . h(self::token()) . '">';
    }

    public static function check(): void
    {
        $sent = $_POST['_csrf'] ?? '';
        if (!is_string($sent) || empty($_SESSION['csrf']) || !hash_equals($_SESSION['csrf'], $sent)) {
            http_response_code(400);
            throw new UserError('The form expired or was sent from another site. Please try again.');
        }
    }
}

// ------------------------------------------------------------------ audit, rate limit, settings

final class Audit
{
    public static function log(string $event, ?int $subjectUserId = null, ?string $detail = null, ?int $actorUserId = null): void
    {
        $actor = $actorUserId ?? (Auth::id() ?: null);
        Db::insert('audit_log', [
            'created_at' => now_utc(),
            'actor_user_id' => $actor,
            'subject_user_id' => $subjectUserId,
            'event' => $event,
            'detail' => $detail === null ? null : mb_substr($detail, 0, 500),
            'ip' => Request::ip(),
        ]);
    }
}

final class RateLimit
{
    /** True if fewer than $max events happened in this bucket for this key within $seconds. */
    public static function allowed(string $bucket, string $key, int $max, int $seconds): bool
    {
        $n = (int)Db::value('SELECT COUNT(*) FROM rate_events WHERE bucket = ? AND key_hash = ? AND created_at > ?',
            [$bucket, hash('sha256', mb_strtolower($key)), gmdate('Y-m-d H:i:s', time() - $seconds)]);
        return $n < $max;
    }

    public static function hit(string $bucket, string $key): void
    {
        Db::insert('rate_events', ['bucket' => $bucket, 'key_hash' => hash('sha256', mb_strtolower($key)), 'created_at' => now_utc()]);
        if (random_int(1, 50) === 1) {   // keep the table small
            Db::run('DELETE FROM rate_events WHERE created_at < ?', [gmdate('Y-m-d H:i:s', time() - 86400 * 2)]);
        }
    }

    /** Variants for the install page, which runs before the tables exist. */
    public static function allowedSafe(string $bucket, string $key, int $max, int $seconds): bool
    {
        try {
            return self::allowed($bucket, $key, $max, $seconds);
        } catch (PDOException) {
            return true;
        }
    }

    public static function hitSafe(string $bucket, string $key): void
    {
        try {
            self::hit($bucket, $key);
        } catch (PDOException) {
        }
    }

    public static function clear(string $bucket, string $key): void
    {
        Db::run('DELETE FROM rate_events WHERE bucket = ? AND key_hash = ?', [$bucket, hash('sha256', mb_strtolower($key))]);
    }
}

final class Settings
{
    public const DEFAULTS = [
        'site_name' => 'Bike Log',
        'registration' => 'open',          // open | invite | closed
        'require_verification' => '1',
        'allowed_email_domains' => '',     // comma list; empty = any
        'maintenance_mode' => '0',          // 1: only admins can sign in
        'notice' => '',                     // banner shown to everyone signed in
    ];
    private static ?array $cache = null;

    public static function get(string $name): string
    {
        if (self::$cache === null) {
            self::$cache = [];
            try {
                foreach (Db::all('SELECT name, value FROM site_settings') as $r) {
                    self::$cache[$r['name']] = $r['value'];
                }
            } catch (PDOException) {
                // not installed yet
            }
        }
        return self::$cache[$name] ?? self::DEFAULTS[$name] ?? '';
    }

    public static function set(string $name, string $value): void
    {
        Db::run('INSERT INTO site_settings (name, value) VALUES (?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value)', [$name, $value]);
        self::$cache = null;
    }

    public static function reset(): void
    {
        self::$cache = null;
    }
}

// ------------------------------------------------------------------ schema migrations

final class Migrator
{
    public static function dir(): string
    {
        return __DIR__ . '/../sql/migrations';
    }

    public static function applied(): array
    {
        try {
            return Db::run('SELECT version FROM schema_migrations ORDER BY version')->fetchAll(PDO::FETCH_COLUMN);
        } catch (PDOException) {
            return [];
        }
    }

    public static function pending(): array
    {
        $done = array_flip(self::applied());
        $out = [];
        foreach (glob(self::dir() . '/*.sql') ?: [] as $f) {
            $v = basename($f, '.sql');
            if (!isset($done[$v])) {
                $out[$v] = $f;
            }
        }
        ksort($out);
        return $out;
    }

    /** Apply pending migrations in order. MySQL DDL commits implicitly, so each file is applied whole. */
    public static function migrate(): array
    {
        Db::pdo()->exec('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(64) PRIMARY KEY, applied_at DATETIME NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
        $applied = [];
        foreach (self::pending() as $v => $file) {
            foreach (self::statements((string)file_get_contents($file)) as $sql) {
                Db::pdo()->exec($sql);
            }
            Db::insert('schema_migrations', ['version' => $v, 'applied_at' => now_utc()]);
            $applied[] = $v;
        }
        return $applied;
    }

    /** Split a migration file on ';' at line ends, ignoring '--' comment lines. */
    public static function statements(string $sql): array
    {
        $lines = [];
        foreach (preg_split('/\R/', $sql) as $line) {
            if (preg_match('/^\s*--/', $line)) {
                continue;
            }
            $lines[] = $line;
        }
        $parts = preg_split('/;\s*(\R|$)/', implode("\n", $lines));
        return array_values(array_filter(array_map('trim', $parts), fn($s) => $s !== ''));
    }
}
