<?php
declare(strict_types=1);

// Bike Log (PHP) test suite. Needs a MySQL/MariaDB server and PHP's built-in web server.
//
//   BIKELOG_TEST_DB_HOST=127.0.0.1 BIKELOG_TEST_DB_USER=bikelog BIKELOG_TEST_DB_PASS=... php tests/run.php
//
// It creates (and drops) the database "bikelog_test" (override with BIKELOG_TEST_DB_NAME), so the user
// needs CREATE/DROP rights on it. Never point it at a real database.

$root = dirname(__DIR__);
$dbName = getenv('BIKELOG_TEST_DB_NAME') ?: 'bikelog_test';
if (!str_contains($dbName, 'test')) {
    fwrite(STDERR, "Refusing: the test database name must contain 'test'.\n");
    exit(2);
}
$tmp = sys_get_temp_dir() . '/bikelog-test-' . getmypid();
@mkdir($tmp, 0700, true);
$cfgFile = "$tmp/config.php";
$cfg = [
    'db' => ['host' => getenv('BIKELOG_TEST_DB_HOST') ?: '127.0.0.1', 'port' => (int)(getenv('BIKELOG_TEST_DB_PORT') ?: 3306),
        'name' => $dbName, 'user' => getenv('BIKELOG_TEST_DB_USER') ?: 'bikelog', 'pass' => getenv('BIKELOG_TEST_DB_PASS') ?: ''],
    'base_url' => 'http://127.0.0.1:8099',
    'install_key' => 'test-install-key-0123456789',
    'force_https' => false,
    'trust_proxy_headers' => false,
    'mail' => ['transport' => 'log', 'from' => 'bikelog@example.test', 'from_name' => 'Bike Log'],
    'storage_dir' => $tmp,
    'default_timezone' => 'Europe/Berlin',
];
file_put_contents($cfgFile, '<?php return ' . var_export($cfg, true) . ';');
putenv("BIKELOG_CONFIG=$cfgFile");

$pdo = new PDO(sprintf('mysql:host=%s;port=%d;charset=utf8mb4', $cfg['db']['host'], $cfg['db']['port']), $cfg['db']['user'], $cfg['db']['pass']);
$pdo->exec("DROP DATABASE IF EXISTS `$dbName`");
$pdo->exec("CREATE DATABASE `$dbName` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");

require $root . '/app/bootstrap.php';

$GLOBALS['passed'] = 0;
$GLOBALS['failed'] = [];
function check(bool $cond, string $what): void
{
    if ($cond) {
        $GLOBALS['passed']++;
    } else {
        $GLOBALS['failed'][] = $what;
        $bt = debug_backtrace()[0];
        fwrite(STDERR, "FAIL: $what (line {$bt['line']})\n");
    }
}
function check_throws(callable $fn, string $what, string $contains = ''): void
{
    try {
        $fn();
        check(false, "$what (no error)");
    } catch (Throwable $e) {
        check($contains === '' || str_contains($e->getMessage(), $contains), "$what: got '" . $e->getMessage() . "'");
    }
}

// ------------------------------------------------------------------ HTTP client (one per browser)

final class Browser
{
    private string $jar;
    public int $status = 0;
    public string $body = '';
    public array $headers = [];

    public function __construct(private string $base)
    {
        $this->jar = tempnam(sys_get_temp_dir(), 'jar');
    }

    public function get(string $query): string
    {
        return $this->req('GET', $query);
    }

    /** POST with the CSRF token of the session (taken from any page). */
    public function post(string $query, array $data, bool $csrf = true): string
    {
        if ($csrf && !isset($data['_csrf'])) {
            $data['_csrf'] = $this->csrf();
        }
        return $this->req('POST', $query, $data);
    }

    /** Multipart POST with files: $files = [field name => [[file name, content], ...]] ("files[]" for a list). */
    public function upload(string $query, array $data, array $files): string
    {
        $data['_csrf'] = $this->csrf();
        $tmpDir = sys_get_temp_dir();
        foreach ($files as $field => $list) {
            foreach (array_values($list) as $i => [$name, $content]) {
                $f = tempnam($tmpDir, 'up');
                file_put_contents($f, $content);
                // "files[]" sends a list (files[0], files[1] ...), "file" one file
                $key = str_ends_with($field, '[]') ? substr($field, 0, -2) . "[$i]" : $field;
                $data[$key] = new CURLFile($f, 'application/json', $name);
            }
        }
        return $this->req('POST', $query, $data, true);
    }

    public function csrf(): string
    {
        $page = $this->req('GET', 'r=login');
        if (!preg_match('/name="_csrf" value="([0-9a-f]+)"/', $page, $m)) {
            $page = $this->req('GET', 'r=account');
            preg_match('/name="_csrf" value="([0-9a-f]+)"/', $page, $m);
        }
        return $m[1] ?? '';
    }

    private function req(string $method, string $query, array $data = [], bool $multipart = false): string
    {
        $url = $this->base . '/index.php' . ($query !== '' ? '?' . $query : '');
        for ($i = 0; $i < 5; $i++) {
            $ch = curl_init($url);
            curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_HEADER => true, CURLOPT_COOKIEJAR => $this->jar,
                CURLOPT_COOKIEFILE => $this->jar, CURLOPT_FOLLOWLOCATION => false, CURLOPT_TIMEOUT => 20,
                CURLOPT_HTTPHEADER => ['Referer: ' . $url]]);
            if ($method === 'POST') {
                curl_setopt($ch, CURLOPT_POST, true);
                curl_setopt($ch, CURLOPT_POSTFIELDS, $multipart ? $data : http_build_query($data));
            }
            $raw = (string)curl_exec($ch);
            $this->status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
            $hs = (int)curl_getinfo($ch, CURLINFO_HEADER_SIZE);
            curl_close($ch);
            $this->headers = [];
            foreach (explode("\r\n", substr($raw, 0, $hs)) as $line) {
                if (str_contains($line, ':')) {
                    [$k, $v] = explode(':', $line, 2);
                    $this->headers[strtolower(trim($k))] = trim($v);
                }
            }
            $this->body = substr($raw, $hs);
            if (in_array($this->status, [301, 302, 303], true) && isset($this->headers['location'])) {
                $loc = $this->headers['location'];
                $url = str_starts_with($loc, 'http') ? $loc : $this->base . '/' . ltrim($loc, '/');
                $method = 'GET';
                $data = [];
                $multipart = false;
                continue;
            }
            break;
        }
        return $this->body;
    }
}

function mails(): string
{
    return (string)@file_get_contents(Config::get('storage_dir') . '/mail.log');
}

function last_link(string $route): string
{
    preg_match_all('#index\.php\?r=' . $route . '&(?:t|invite)=([0-9a-f]{64})#', mails(), $m);
    return end($m[1]) ?: '';
}

// ------------------------------------------------------------------ start the web server

$port = 8099;
$cmd = sprintf('BIKELOG_CONFIG=%s exec php -S 127.0.0.1:%d -t %s > %s 2>&1', escapeshellarg($cfgFile), $port, escapeshellarg("$root/public"), escapeshellarg("$tmp/server.log"));
$server = proc_open($cmd, [], $pipes);
for ($i = 0; $i < 50; $i++) {
    if (@fsockopen('127.0.0.1', $port)) {
        break;
    }
    usleep(100000);
}
register_shutdown_function(function () use ($server, $pdo, $dbName, $tmp) {
    proc_terminate($server);
    if (!getenv('BIKELOG_TEST_KEEP')) {
        $pdo->exec("DROP DATABASE IF EXISTS `$dbName`");
        array_map('unlink', glob("$tmp/*") ?: []);
        @rmdir($tmp);
    }
});

$base = "http://127.0.0.1:$port";
foreach (glob(__DIR__ . '/test_*.php') as $file) {
    echo 'Running ' . basename($file) . "\n";
    require $file;
}

$serverLog = (string)@file_get_contents("$tmp/server.log");
if (preg_match('/(PHP (Fatal|Warning|Notice|Deprecated)[^\n]*)/', $serverLog . @file_get_contents("$tmp/php-error.log"), $m)) {
    check(false, 'server log has PHP problems: ' . $m[1]);
}
$errLog = (string)@file_get_contents("$tmp/php-error.log");
if (str_contains($errLog, 'Bike Log error')) {
    check(false, "unexpected server error:\n" . substr($errLog, 0, 2000));
}

echo "\n{$GLOBALS['passed']} checks passed, " . count($GLOBALS['failed']) . " failed.\n";
exit($GLOBALS['failed'] ? 1 : 0);
