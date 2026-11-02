<?php
declare(strict_types=1);

// One user's data as a JSON file (download, backup, restore) and the fresh start.
//
// Nothing is lost: a fresh start and a restore first store a copy of the current data (user_backups),
// which can be restored again. A restore replaces all of the user's data with the file's; every id is
// given a new number and every reference follows, so a file from another server or account works too.

final class UserBackups
{
    public const FORMAT = 'bikelog-php-export';
    public const VERSION = 2;
    public const KEEP = 20;
    public const MAX_UPLOAD = 20 * 1024 * 1024;
    public const CONFIRM_RESET = 'RESET';
    public const CONFIRM_RESTORE = 'RESTORE';

    /** table => [column => referenced table]; in insert order (a table only references tables above it). */
    public const TABLES = [
        'products' => [],
        'work_sessions' => [],
        'bikes' => [],
        'purchase_bundles' => ['work_session_id' => 'work_sessions'],
        'consumables' => ['product_id' => 'products'],
        'components' => ['product_id' => 'products', 'bundle_id' => 'purchase_bundles', 'from_stock_txn_id' => 'consumable_txns',
            'work_session_id' => 'work_sessions', 'rotation_bike_id' => 'bikes'],
        'installations' => ['component_id' => 'components', 'bike_id' => 'bikes', 'parent_component_id' => 'components',
            'work_session_id' => 'work_sessions', 'removal_session_id' => 'work_sessions'],
        'usage_adjustments' => ['component_id' => 'components'],
        'rides' => ['bike_id' => 'bikes'],
        'maintenance_events' => ['component_id' => 'components', 'bike_id' => 'bikes', 'consumable_id' => 'consumables', 'work_session_id' => 'work_sessions'],
        'consumable_txns' => ['consumable_id' => 'consumables', 'maintenance_event_id' => 'maintenance_events', 'work_session_id' => 'work_sessions'],
        'service_rules' => ['component_id' => 'components'],
        'reminder_snoozes' => ['component_id' => 'components', 'bike_id' => 'bikes'],
        'component_dispositions' => ['component_id' => 'components', 'work_session_id' => 'work_sessions'],
        'journal_entries' => ['bike_id' => 'bikes', 'component_id' => 'components', 'ride_id' => 'rides', 'repair_session_id' => 'work_sessions'],
        'service_orders' => ['component_id' => 'components', 'bike_id' => 'bikes', 'from_bike_id' => 'bikes', 'from_parent_id' => 'components',
            'send_session_id' => 'work_sessions', 'return_session_id' => 'work_sessions', 'event_id' => 'maintenance_events', 'replacement_id' => 'components'],
        'pick_list_items' => ['merged_into_id' => 'pick_list_items'],
        'change_log' => ['bike_id' => 'bikes', 'component_id' => 'components'],
    ];
    /** change_log.entity_id points to a different table per entity. */
    private const LOG_ENTITY = ['bike' => 'bikes', 'part' => 'components', 'ride' => 'rides', 'product' => 'products', 'rule' => 'service_rules',
        'supply' => 'consumables', 'installation' => 'installations', 'work' => 'maintenance_events', 'journal' => 'journal_entries',
        'list' => 'pick_list_items', 'data' => 'work_sessions'];
    /** References that may point nowhere (the target was removed for good, e.g. by an undo): set to empty. */
    private const SOFT = ['components.from_stock_txn_id', 'pick_list_items.merged_into_id', 'change_log.bike_id', 'change_log.component_id'];

    private static array $columns = [];

    // ------------------------------------------------------------------ export

    public static function export(int $uid): array
    {
        $u = Db::one('SELECT id, email, display_name, timezone, created_at FROM users WHERE id = ?', [$uid]);
        $out = ['format' => self::FORMAT, 'version' => self::VERSION, 'app_version' => BIKELOG_PHP_VERSION, 'exported_at' => gmdate('c'), 'user' => $u];
        foreach (array_keys(self::TABLES) as $t) {
            $out[$t] = Db::all("SELECT * FROM $t WHERE user_id = ? ORDER BY id", [$uid]);
        }
        $out['user_settings'] = Db::all('SELECT name, value FROM user_settings WHERE user_id = ? ORDER BY name', [$uid]);
        return $out;
    }

    public static function encode(array $data): string
    {
        return json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    }

    public static function summary(array $data): string
    {
        $n = fn(string $t) => count($data[$t] ?? []);
        return sprintf('%d bikes, %d parts, %d rides, %d maintenance entries', $n('bikes'), $n('components'), $n('rides'), $n('maintenance_events'));
    }

    // ------------------------------------------------------------------ stored copies

    public static function save(int $uid, string $reason): int
    {
        $data = self::export($uid);
        $gz = gzencode(self::encode($data), 6);
        $id = Db::insert('user_backups', ['user_id' => $uid, 'created_at' => now_utc(), 'reason' => $reason, 'summary' => self::summary($data),
            'size_bytes' => strlen($gz), 'content' => $gz]);
        $old = Db::all('SELECT id FROM user_backups WHERE user_id = ? ORDER BY id DESC LIMIT 1000 OFFSET ' . self::KEEP, [$uid]);
        if ($old) {
            Db::run('DELETE FROM user_backups WHERE user_id = ? AND id IN (' . implode(',', array_map('intval', array_column($old, 'id'))) . ')', [$uid]);
        }
        return $id;
    }

    public static function rows(int $uid): array
    {
        return Db::all('SELECT id, created_at, reason, summary, size_bytes FROM user_backups WHERE user_id = ? ORDER BY id DESC', [$uid]);
    }

    public static function content(int $uid, int $id): string
    {
        $b = Db::one('SELECT content FROM user_backups WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Backup not found.');
        $json = gzdecode($b['content']);
        if ($json === false) {
            throw new UserError('This backup is damaged.');
        }
        return $json;
    }

    // ------------------------------------------------------------------ fresh start

    /** Store a copy, then remove all of the user's bikes, parts, rides ... and start with the default rules. */
    public static function freshStart(int $uid): int
    {
        return Db::tx(function () use ($uid) {
            $backup = self::save($uid, 'BEFORE_RESET');
            self::wipe($uid);
            Domain::seedUser($uid);
            ChangeLog::note($uid, 'data', null, 'Fresh start (a copy of the data before it is under Backups)');
            return $backup;
        });
    }

    private static function wipe(int $uid): void
    {
        foreach (array_reverse(array_keys(self::TABLES)) as $t) {
            Db::run("DELETE FROM $t WHERE user_id = ?", [$uid]);
        }
        Db::run('DELETE FROM user_settings WHERE user_id = ?', [$uid]);
    }

    // ------------------------------------------------------------------ restore

    private static function columns(string $table): array
    {
        return self::$columns[$table] ??= array_column(Db::all("SHOW COLUMNS FROM $table"), null, 'Field');
    }

    public static function parse(string $content): array
    {
        if (str_starts_with($content, "\x1f\x8b")) {
            $content = (string)@gzdecode($content);
        }
        try {
            $d = json_decode($content, true, 64, JSON_THROW_ON_ERROR);
        } catch (JsonException $e) {
            throw new UserError('This is not a Bike Log data file (not valid JSON).');
        }
        if (!is_array($d) || ($d['format'] ?? null) !== self::FORMAT) {
            throw new UserError('This is not a Bike Log data file from the web version (Account → Download all my data).');
        }
        if (!is_int($d['version'] ?? null) || $d['version'] > self::VERSION) {
            throw new UserError('This file comes from a newer Bike Log. Update the app first.');
        }
        return $d;
    }

    /** Check the file and plan new ids. Returns [plan, warnings]; throws UserError with every problem found. */
    public static function check(array $d): array
    {
        $errors = [];
        $warnings = [];
        $ids = [];
        foreach (self::TABLES as $t => $refs) {
            $rows = $d[$t] ?? [];
            if (!is_array($rows) || ($rows && !array_is_list($rows))) {
                $errors[] = "$t: expected a list";
                continue;
            }
            $cols = self::columns($t);
            $unknown = [];
            foreach ($rows as $i => $r) {
                if (!is_array($r) || !isset($r['id']) || !ctype_digit((string)$r['id'])) {
                    $errors[] = "$t[$i]: row without an id";
                    continue;
                }
                if (isset($ids[$t][(string)$r['id']])) {
                    $errors[] = "$t: id {$r['id']} twice";
                }
                $ids[$t][(string)$r['id']] = true;
                foreach ($r as $k => $v) {
                    if (!isset($cols[$k])) {
                        $unknown[$k] = true;
                    } elseif ($v !== null && !is_scalar($v)) {
                        $errors[] = "$t[$i].$k: not a plain value";
                    }
                }
                foreach ($cols as $name => $c) {
                    if ($name !== 'id' && $name !== 'user_id' && $c['Null'] === 'NO' && $c['Default'] === null && !str_contains((string)$c['Extra'], 'auto_increment')
                        && !array_key_exists($name, $r)) {
                        $errors[] = "$t[$i]: $name is missing";
                    }
                }
            }
            if ($unknown) {
                $warnings[] = "$t: left out fields this version does not know: " . implode(', ', array_keys($unknown));
            }
        }
        // every reference must point to a row in the file
        foreach (self::TABLES as $t => $refs) {
            foreach ($d[$t] ?? [] as $i => $r) {
                if (!is_array($r)) {
                    continue;
                }
                foreach ($refs as $col => $target) {
                    $v = $r[$col] ?? null;
                    if ($v !== null && $v !== '' && !isset($ids[$target][(string)$v]) && !in_array("$t.$col", self::SOFT, true)) {
                        $errors[] = "$t[$i].$col: points to $target {$v}, which is not in the file";
                    }
                }
            }
        }
        if (isset($d['user_settings']) && !is_array($d['user_settings'])) {
            $errors[] = 'user_settings: expected a list';
        }
        if ($errors) {
            throw new UserError('The file cannot be restored: ' . implode('; ', array_slice($errors, 0, 20)) . (count($errors) > 20 ? ' …' : ''));
        }
        return [$ids, $warnings];
    }

    /** Replace all of the user's data with the file's. A copy of the current data is stored first. */
    public static function restore(int $uid, array $d, string $label): array
    {
        [$ids, $warnings] = self::check($d);
        $prevOff = ChangeLog::$off;
        try {
            $result = Db::tx(function () use ($uid, $d, $ids, $label) {
                $backup = self::save($uid, 'BEFORE_RESTORE');
                self::wipe($uid);
                ChangeLog::$off = true;
                // new ids: above the current highest id of each table (rows lock the end of the index)
                $map = [];
                foreach ($ids as $t => $old) {
                    $base = (int)Db::value("SELECT COALESCE(MAX(id), 0) FROM $t FOR UPDATE");
                    $keys = array_keys($old);
                    sort($keys, SORT_NUMERIC);
                    foreach ($keys as $n => $k) {
                        $map[$t][(string)$k] = $base + $n + 1;
                    }
                }
                foreach (self::TABLES as $t => $refs) {
                    $cols = self::columns($t);
                    foreach ($d[$t] ?? [] as $r) {
                        $row = array_intersect_key($r, $cols);
                        $row['id'] = $map[$t][(string)$r['id']];
                        $row['user_id'] = $uid;
                        foreach ($refs as $col => $target) {
                            if (isset($row[$col]) && $row[$col] !== '') {
                                $row[$col] = $map[$target][(string)$row[$col]] ?? null;
                            }
                        }
                        if ($t === 'change_log' && isset($row['entity_id'])) {
                            $target = self::LOG_ENTITY[$row['entity'] ?? ''] ?? null;
                            $row['entity_id'] = $target ? ($map[$target][(string)$row['entity_id']] ?? null) : null;
                        }
                        $names = array_keys($row);
                        Db::run(sprintf('INSERT INTO %s (%s) VALUES (%s)', $t, implode(',', $names), implode(',', array_fill(0, count($names), '?'))),
                            array_values($row));
                    }
                }
                foreach ($d['user_settings'] ?? [] as $s) {
                    if (is_array($s) && is_string($s['name'] ?? null) && is_scalar($s['value'] ?? null)) {
                        UserSettings::set($uid, mb_substr($s['name'], 0, 64), (string)$s['value']);
                    }
                }
                ChangeLog::$off = false;
                ChangeLog::note($uid, 'data', null, "Restored from $label (" . self::summary($d) . ')');
                return $backup;
            });
        } finally {
            ChangeLog::$off = $prevOff;
        }
        return ['backup_id' => $result, 'warnings' => $warnings, 'summary' => self::summary($d)];
    }
}
