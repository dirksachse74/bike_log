<?php
declare(strict_types=1);

// Pick lists (shop names you pick instead of typing again) and the change log (what changed, field by field).

final class PickLists
{
    public const LISTS = [
        'SHOP' => [
            'name' => 'Shops',
            'hint' => 'Where you buy parts and supplies, where parts go for repair, and who did the work.',
            'columns' => [['components', 'shop'], ['maintenance_events', 'shop'], ['purchase_bundles', 'merchant'], ['service_orders', 'shop']],
        ],
    ];

    private static function check(string $code): array
    {
        return self::LISTS[$code] ?? throw new NotFound(t('No such list.'));
    }

    private static function clean(?string $name): ?string
    {
        $n = trim(preg_replace('/\s+/u', ' ', (string)$name));
        return $n === '' ? null : mb_substr($n, 0, 160);
    }

    private static function find(int $uid, string $code, string $name): ?array
    {
        // the table collation ignores upper/lower case, so "Bike-Components.de" finds "bike-components.de"
        return Db::one('SELECT * FROM pick_list_items WHERE user_id = ? AND list_code = ? AND name = ?', [$uid, $code, $name]);
    }

    private static function final(int $uid, array $item): array
    {
        $seen = [];
        while ($item['merged_into_id'] && !isset($seen[$item['id']])) {
            $seen[$item['id']] = true;
            $next = Db::one('SELECT * FROM pick_list_items WHERE id = ? AND user_id = ?', [$item['merged_into_id'], $uid]);
            if (!$next) {
                break;
            }
            $item = $next;
        }
        return $item;
    }

    /** The list's spelling of a name (a merged name gives the name it went into); a new name is added. */
    public static function canonical(int $uid, string $code, ?string $name): ?string
    {
        self::check($code);
        $name = self::clean($name);
        if ($name === null) {
            return null;
        }
        $item = self::find($uid, $code, $name);
        if (!$item) {
            Db::run('INSERT IGNORE INTO pick_list_items (user_id, list_code, name, created_at) VALUES (?,?,?,?)', [$uid, $code, $name, now_utc()]);
            return $name;
        }
        $item = self::final($uid, $item);
        if ($item['hidden_at'] !== null && !$item['merged_into_id']) {
            Db::run('UPDATE pick_list_items SET hidden_at = NULL WHERE id = ?', [$item['id']]);   // typed again: offered again
        }
        return $item['name'];
    }

    /** Names already used on records but not on the list yet (data from before the list existed, restores). */
    public static function sync(int $uid, string $code): void
    {
        foreach (self::check($code)['columns'] as [$table, $col]) {
            foreach (Db::all("SELECT DISTINCT $col AS n FROM $table WHERE user_id = ? AND $col IS NOT NULL AND $col <> ''", [$uid]) as $r) {
                $n = self::clean($r['n']);
                if ($n !== null) {
                    Db::run('INSERT IGNORE INTO pick_list_items (user_id, list_code, name, created_at) VALUES (?,?,?,?)', [$uid, $code, $n, now_utc()]);
                }
            }
        }
    }

    /** Names on offer in the dropdowns. */
    public static function names(int $uid, string $code = 'SHOP'): array
    {
        return array_column(Db::all('SELECT name FROM pick_list_items WHERE user_id = ? AND list_code = ? AND hidden_at IS NULL
            AND merged_into_id IS NULL ORDER BY name', [$uid, $code]), 'name');
    }

    private static function uses(int $uid, string $code, string $name): int
    {
        $n = 0;
        foreach (self::check($code)['columns'] as [$table, $col]) {
            $n += (int)Db::value("SELECT COUNT(*) FROM $table WHERE user_id = ? AND $col = ?", [$uid, $name]);
        }
        return $n;
    }

    public static function rows(int $uid, string $code): array
    {
        self::sync($uid, $code);
        $rows = Db::all('SELECT p.*, m.name AS merged_into FROM pick_list_items p LEFT JOIN pick_list_items m ON m.id = p.merged_into_id
            WHERE p.user_id = ? AND p.list_code = ? ORDER BY p.merged_into_id IS NOT NULL, p.hidden_at IS NOT NULL, p.name', [$uid, $code]);
        foreach ($rows as &$r) {
            $r['uses'] = self::uses($uid, $code, $r['name']);
        }
        return $rows;
    }

    private static function item(int $uid, int $id): array
    {
        return Db::one('SELECT * FROM pick_list_items WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound(t('Not found.'));
    }

    public static function add(int $uid, string $code, string $name): void
    {
        self::check($code);
        $name = self::clean($name) ?? throw new UserError(t('Please type a name.'));
        if (self::find($uid, $code, $name)) {
            throw new UserError(t('“{name}” is on the list already.', ['name' => $name]));
        }
        Db::insert('pick_list_items', ['user_id' => $uid, 'list_code' => $code, 'name' => $name, 'created_at' => now_utc()]);
    }

    /** Rename an entry; every record using the old name follows. */
    public static function rename(int $uid, int $id, string $name): int
    {
        return Db::tx(function () use ($uid, $id, $name) {
            $it = self::item($uid, $id);
            $name = self::clean($name) ?? throw new UserError(t('Please type a name.'));
            $other = self::find($uid, $it['list_code'], $name);
            if ($other && (int)$other['id'] !== $id) {
                throw new UserError(t('“{name}” is on the list already. Use Merge to put the two together.', ['name' => $name]));
            }
            $n = self::moveRecords($uid, $it['list_code'], $it['name'], $name);
            Db::run('UPDATE pick_list_items SET name = ? WHERE id = ?', [$name, $id]);
            ChangeLog::note($uid, 'list', $id, t('Renamed “{old}” to “{new}” ({n} records)', ['old' => $it['name'], 'new' => $name, 'n' => $n]));
            return $n;
        });
    }

    /** Records with the duplicate's name move to the kept name; the duplicate stays, marked as merged. */
    public static function merge(int $uid, int $id, int $intoId): int
    {
        return Db::tx(function () use ($uid, $id, $intoId) {
            $it = self::item($uid, $id);
            $into = self::final($uid, self::item($uid, $intoId));
            if ((int)$into['id'] === $id || $into['list_code'] !== $it['list_code']) {
                throw new UserError(t('Pick another name to merge into.'));
            }
            $n = self::moveRecords($uid, $it['list_code'], $it['name'], $into['name']);
            Db::run('UPDATE pick_list_items SET merged_into_id = ?, hidden_at = COALESCE(hidden_at, ?) WHERE id = ?', [$into['id'], now_utc(), $id]);
            Db::run('UPDATE pick_list_items SET merged_into_id = ? WHERE merged_into_id = ? AND user_id = ?', [$into['id'], $id, $uid]);
            ChangeLog::note($uid, 'list', $id, t('Merged “{old}” into “{new}” ({n} records)', ['old' => $it['name'], 'new' => $into['name'], 'n' => $n]));
            return $n;
        });
    }

    public static function hide(int $uid, int $id, bool $hide): void
    {
        $it = self::item($uid, $id);
        if (!$hide && $it['merged_into_id']) {
            throw new UserError(t('A merged name stays hidden. Rename the kept name instead.'));
        }
        Db::run('UPDATE pick_list_items SET hidden_at = ? WHERE id = ?', [$hide ? now_utc() : null, $id]);
    }

    private static function moveRecords(int $uid, string $code, string $from, string $to): int
    {
        $n = 0;
        foreach (self::check($code)['columns'] as [$table, $col]) {
            $n += Db::run("UPDATE $table SET $col = ? WHERE user_id = ? AND $col = ?", [$to, $uid, $from])->rowCount();
        }
        return $n;
    }

    /** Db hook: shop names on records are stored in the list's spelling. */
    public static function beforeWrite(string $table, array $row, int $uid): array
    {
        foreach (self::LISTS as $code => $l) {
            foreach ($l['columns'] as [$t, $col]) {
                if ($t === $table && array_key_exists($col, $row) && is_string($row[$col])) {
                    $row[$col] = self::canonical($uid, $code, $row[$col]);
                }
            }
        }
        return $row;
    }
}

final class ChangeLog
{
    /** table => [entity, label of what it is] */
    public const TRACKED = [
        'bikes' => ['bike', 'Bike'], 'components' => ['part', 'Part'], 'rides' => ['ride', 'Ride'], 'products' => ['product', 'Product'],
        'service_rules' => ['rule', 'Service rule'], 'consumables' => ['supply', 'Supply'], 'installations' => ['installation', 'Fitted'],
        'maintenance_events' => ['work', 'Work done'], 'journal_entries' => ['journal', 'Journal'],
    ];
    public const ENTITY_LABELS = ['bike' => 'Bike', 'part' => 'Part', 'ride' => 'Ride', 'product' => 'Product', 'rule' => 'Service rule',
        'supply' => 'Supply', 'installation' => 'Fitted', 'work' => 'Work done', 'journal' => 'Journal', 'list' => 'Shops', 'data' => 'Your data'];
    private const SKIP = ['updated_at', 'created_at', 'user_id', 'id', 'specs_json'];

    public static bool $off = false;
    public static string $source = 'FORM';

    public static function register(): void
    {
        Db::$trackedTables = array_keys(self::TRACKED);
        Db::$beforeWrite = fn(string $t, array $row, int $uid) => PickLists::beforeWrite($t, $row, $uid);
        Db::$afterWrite = function (string $t, int $id, int $uid, array $row, ?array $old) {
            if (!self::$off && isset(self::TRACKED[$t])) {
                $old === null ? self::created($t, $id, $uid, $row) : self::changed($t, $id, $uid, $row, $old);
            }
        };
    }

    private static function write(int $uid, string $entity, ?int $entityId, string $action, ?string $field, ?string $old, ?string $new,
                                  ?int $bikeId = null, ?int $componentId = null): void
    {
        Db::run('INSERT INTO change_log (user_id, changed_at, entity, entity_id, bike_id, component_id, action, field, old_value, new_value, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)', [$uid, now_utc(), $entity, $entityId, $bikeId, $componentId, $action, $field,
            $old === null ? null : mb_substr($old, 0, 500), $new === null ? null : mb_substr($new, 0, 500), self::$source]);
    }

    /** A free-text line (a part taken off, a work step undone, a fresh start). */
    public static function note(int $uid, string $entity, ?int $id, string $text, ?int $bikeId = null, ?int $componentId = null): void
    {
        if (!self::$off) {
            self::write($uid, $entity, $id, 'NOTE', null, null, $text, $bikeId, $componentId);
        }
    }

    private static function context(string $table, int $id, array $row, ?array $old = null): array
    {
        $all = $row + ($old ?? []);
        return match ($table) {
            'bikes' => [$id, null],
            'components' => [null, $id],
            'installations', 'maintenance_events', 'journal_entries' => [isset($all['bike_id']) ? (int)$all['bike_id'] : null,
                isset($all['component_id']) ? (int)$all['component_id'] : null],
            'rides' => [isset($all['bike_id']) ? (int)$all['bike_id'] : null, null],
            'service_rules' => [null, isset($all['component_id']) ? (int)$all['component_id'] : null],
            default => [null, null],
        };
    }

    private static function created(string $t, int $id, int $uid, array $row): void
    {
        [$bike, $comp] = self::context($t, $id, $row);
        $text = match ($t) {
            'bikes', 'consumables', 'service_rules' => $row['name'] ?? null,
            'components' => $row['label'] ?? null,
            'products' => trim(($row['maker'] ?? '') . ' ' . ($row['model'] ?? '')),
            'rides' => trim(($row['ride_date'] ?? '') . ' ' . (isset($row['distance_km']) && $row['distance_km'] !== null ? km((float)$row['distance_km'], 1) : '')),
            'installations' => t('{where} from {date}', ['where' => self::where($uid, $row), 'date' => $row['installed_on'] ?? '']),
            'maintenance_events' => t('{what} on {date}', ['what' => Catalog::actionName((string)($row['action_code'] ?? '')), 'date' => $row['performed_on'] ?? '']),
            'journal_entries' => mb_substr((string)($row['text'] ?? ''), 0, 120),
            default => null,
        };
        self::write($uid, self::TRACKED[$t][0], $id, 'CREATED', null, null, $text, $bike, $comp);
    }

    private static function where(int $uid, array $row): string
    {
        if (!empty($row['bike_id'])) {
            $n = Db::value('SELECT name FROM bikes WHERE id = ? AND user_id = ?', [$row['bike_id'], $uid]);
            return t('On {where}', ['where' => $n ?? t('a bike')]) . ' (' . ($row['slot'] ?? '') . ')';
        }
        $n = Db::value('SELECT label FROM components WHERE id = ? AND user_id = ?', [$row['parent_component_id'] ?? 0, $uid]);
        return t('On {where}', ['where' => $n ?? t('a part')]) . ' (' . ($row['slot'] ?? '') . ')';
    }

    private static function changed(string $t, int $id, int $uid, array $row, array $old): void
    {
        [$bike, $comp] = self::context($t, $id, $row, $old);
        foreach ($row as $f => $v) {
            if (in_array($f, self::SKIP, true) || !array_key_exists($f, $old)) {
                continue;
            }
            $a = self::show($uid, $f, $old[$f]);
            $b = self::show($uid, $f, $v);
            if ($a !== $b) {
                self::write($uid, self::TRACKED[$t][0], $id, 'CHANGED', $f, $a, $b, $bike, $comp);
            }
        }
    }

    private static function show(int $uid, string $field, mixed $v): ?string
    {
        if ($v === null || $v === '') {
            return null;
        }
        if (str_ends_with($field, '_cents')) {
            return money((int)$v);
        }
        if ($field === 'bike_id' || $field === 'rotation_bike_id') {
            return (string)(Db::value('SELECT name FROM bikes WHERE id = ? AND user_id = ?', [$v, $uid]) ?? t('bike {id}', ['id' => $v]));
        }
        if ($field === 'product_id') {
            $p = Db::one('SELECT maker, model FROM products WHERE id = ? AND user_id = ?', [$v, $uid]);
            return $p ? trim($p['maker'] . ' ' . $p['model']) : t('product {id}', ['id' => $v]);
        }
        if (is_numeric($v) && str_contains((string)$v, '.')) {
            return rtrim(rtrim((string)$v, '0'), '.');   // 12.50 and 12.5 are the same value
        }
        return (string)$v;
    }

    public static function fieldLabel(?string $f): string
    {
        if ($f === null) {
            return '';
        }
        $f = preg_replace('/_(cents|id|json)$/', '', $f);
        return t(ucfirst(str_replace('_', ' ', $f)));
    }

    public static function entries(int $uid, ?int $bikeId = null, ?int $componentId = null, ?string $entity = null, int $limit = 200, int $beforeId = 0): array
    {
        $where = ['user_id = ?'];
        $p = [$uid];
        if ($bikeId) {
            $where[] = 'bike_id = ?';
            $p[] = $bikeId;
        }
        if ($componentId) {
            $where[] = 'component_id = ?';
            $p[] = $componentId;
        }
        if ($entity) {
            $where[] = 'entity = ?';
            $p[] = $entity;
        }
        if ($beforeId) {
            $where[] = 'id < ?';
            $p[] = $beforeId;
        }
        $limit = max(1, min(1000, $limit));
        return Db::all('SELECT * FROM change_log WHERE ' . implode(' AND ', $where) . " ORDER BY id DESC LIMIT $limit", $p);
    }
}
