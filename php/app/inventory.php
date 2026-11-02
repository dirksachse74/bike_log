<?php
declare(strict_types=1);

// Products, what happens to removed parts, work sessions (undo), frames and wheels that always exist,
// counted spare stock, spare minimums and the shopping list. Same rules as the desktop app's
// services/inventory.py, stock.py, frames.py, wheels.py and worksessions.py.

final class UserSettings
{
    public const DEFAULTS = [
        'spare_minimums' => '{"INNER_TUBE": 2, "TIRE": 1}',
        'spoke_relace_after' => '3',
        'default_tire_setup' => 'TUBE',
    ];

    public static function get(int $uid, string $name): string
    {
        $v = Db::value('SELECT value FROM user_settings WHERE user_id = ? AND name = ?', [$uid, $name]);
        return $v ?? (self::DEFAULTS[$name] ?? '');
    }

    public static function set(int $uid, string $name, string $value): void
    {
        Db::run('INSERT INTO user_settings (user_id, name, value) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value)', [$uid, $name, $value]);
    }

    /** @return array<string,int> part type => how many spares to keep */
    public static function spareMinimums(int $uid): array
    {
        $d = json_decode(self::get($uid, 'spare_minimums'), true);
        return is_array($d) ? array_map('intval', $d) : [];
    }
}

final class Inventory
{
    public const AUTO_FRAME_NOTE = 'Added with the bike (frame and fork are one part)';
    public const AUTO_WHEEL_NOTE = 'Added with the wheelset (a wheelset has a front and a rear wheel)';

    public static function dispositions(): array
    {
        $d = Catalog::raw('dispositions');
        unset($d['IN_USE']);
        return $d;
    }

    // ------------------------------------------------------------------ products

    public static function findProduct(int $uid, string $type, ?string $maker, string $model): ?array
    {
        return Db::one('SELECT * FROM products WHERE user_id = ? AND component_type = ? AND LOWER(COALESCE(maker, \'\')) = LOWER(?) AND LOWER(model) = LOWER(?) ORDER BY id LIMIT 1',
            [$uid, $type, (string)$maker, $model]);
    }

    public static function productFor(int $uid, string $type, ?string $maker, string $model, array $specs = [], ?string $source = null, ?string $version = null, ?string $notes = null): int
    {
        $p = self::findProduct($uid, $type, $maker, $model);
        if ($p) {
            return (int)$p['id'];
        }
        return Db::insert('products', ['user_id' => $uid, 'component_type' => $type, 'maker' => $maker, 'model' => $model,
            'specs_json' => $specs ? json_encode($specs, JSON_UNESCAPED_UNICODE) : null, 'spec_source' => $source, 'spec_version' => $version,
            'notes' => $notes, 'created_at' => now_utc()]);
    }

    /** A new part. Returns its id. */
    public static function createComponent(int $uid, array $f): int
    {
        $now = now_utc();
        return Db::insert('components', [
            'user_id' => $uid, 'component_type' => $f['component_type'], 'label' => mb_substr($f['label'], 0, 160),
            'product_id' => $f['product_id'] ?? null, 'maker' => $f['maker'] ?? null, 'model' => $f['model'] ?? null,
            'mark' => $f['mark'] ?? null, 'prior_usage' => $f['prior_usage'] ?? 'NEW', 'starting_km' => $f['starting_km'] ?? null,
            'purchase_date' => $f['purchase_date'] ?? null, 'price_cents' => $f['price_cents'] ?? null, 'shop' => $f['shop'] ?? null,
            'notes' => $f['notes'] ?? null, 'tire_setup' => $f['tire_setup'] ?? null, 'work_session_id' => $f['work_session_id'] ?? null,
            'serial_number' => $f['serial_number'] ?? null, 'storage_location' => $f['storage_location'] ?? null,
            'created_at' => $now, 'updated_at' => $now,
        ]);
    }

    /** "Ultegra chain", or "Ultegra chain (2)" when the name is taken (tires and tubes may share names). */
    public static function uniqueLabel(int $uid, string $type, string $base, array &$taken = []): string
    {
        $used = function (string $l) use ($uid, $type, $taken) {
            if (in_array($type, ['TIRE', 'INNER_TUBE'], true)) {
                return false;
            }
            return isset($taken[mb_strtolower($l)]) || Db::one('SELECT id FROM components WHERE user_id = ? AND component_type = ? AND LOWER(label) = LOWER(?)', [$uid, $type, $l]);
        };
        $label = $base;
        $n = 2;
        while ($used($label)) {
            $label = "$base ($n)";
            $n++;
        }
        $taken[mb_strtolower($label)] = true;
        return $label;
    }

    // ------------------------------------------------------------------ what happened to a part

    public static function setDisposition(int $uid, int $componentId, string $disposition, string $on, ?string $note = null, ?int $ws = null): void
    {
        if (!isset(self::dispositions()[$disposition])) {
            throw new UserError('Unknown choice for what happened to the part.');
        }
        $c = Domain::component($uid, $componentId);
        Db::insert('component_dispositions', ['user_id' => $uid, 'component_id' => $componentId, 'disposition' => $disposition,
            'previous_disposition' => $c['disposition'], 'effective_on' => $on, 'note' => $note, 'work_session_id' => $ws, 'created_at' => now_utc()]);
        $retire = in_array($disposition, ['RETIRED', 'DISCARDED', 'SOLD', 'WARRANTY_RETURN'], true);
        Db::updateOwned('components', $componentId, $uid, ['disposition' => $disposition, 'disposition_on' => $on, 'updated_at' => now_utc()]
            + ($retire ? ['status' => 'RETIRED', 'retired_on' => $on, 'retire_reason' => $note ?: (self::dispositions()[$disposition] ?? $disposition)]
                : ['status' => 'ACTIVE', 'retired_on' => null, 'retire_reason' => null]));
    }

    /** Take a part off (on the date) and record what happened to it (stored, awaiting service, discarded ...). */
    public static function removeWithOutcome(int $uid, int $installationId, string $on, string $outcome, ?string $reason = null, ?int $ws = null): void
    {
        Db::tx(function () use ($uid, $installationId, $on, $outcome, $reason, $ws) {
            $i = Db::one('SELECT * FROM installations WHERE id = ? AND user_id = ?', [$installationId, $uid]) ?? throw new NotFound('Record not found.');
            Domain::remove($uid, $installationId, $on, $reason);
            Db::run('UPDATE installations SET removal_outcome = ?, removal_session_id = ? WHERE id = ?', [$outcome, $ws, $installationId]);
            self::setDisposition($uid, (int)$i['component_id'], $outcome, $on, $reason, $ws);
        });
    }

    public static function defaultOutcome(string $type): string
    {
        return Catalog::type($type)['removed_default'] ?? 'STORED';
    }

    // ------------------------------------------------------------------ work sessions

    public static function startSession(int $uid, string $kind, string $title, string $on): int
    {
        return Db::insert('work_sessions', ['user_id' => $uid, 'kind' => $kind, 'title' => mb_substr($title, 0, 200),
            'happened_on' => $on, 'created_at' => now_utc()]);
    }

    /**
     * Undo everything a work session did: parts it created disappear (they never existed), installations it
     * made are voided, removals it made are reopened, dispositions go back, stock and maintenance are voided.
     */
    public static function undoSession(int $uid, int $wsId): void
    {
        Db::tx(function () use ($uid, $wsId) {
            $ws = Db::one('SELECT * FROM work_sessions WHERE id = ? AND user_id = ? AND undone_at IS NULL', [$wsId, $uid])
                ?? throw new UserError('This was already undone.');
            $now = now_utc();
            $created = array_map('intval', array_column(Db::all('SELECT id FROM components WHERE user_id = ? AND work_session_id = ?', [$uid, $wsId]), 'id'));
            foreach ($created as $cid) {
                $outside = (int)Db::value('SELECT (SELECT COUNT(*) FROM installations WHERE component_id = ? AND (work_session_id IS NULL OR work_session_id <> ?) AND voided_at IS NULL)
                    + (SELECT COUNT(*) FROM maintenance_events WHERE component_id = ? AND (work_session_id IS NULL OR work_session_id <> ?) AND voided_at IS NULL)',
                    [$cid, $wsId, $cid, $wsId]);
                if ($outside > 0) {
                    throw new UserError('A part from this step has newer history; undo or correct that first.');
                }
            }
            Db::run('UPDATE installations SET voided_at = ?, void_reason = ? WHERE user_id = ? AND work_session_id = ? AND voided_at IS NULL', [$now, 'undone: ' . $ws['title'], $uid, $wsId]);
            Db::run('UPDATE installations SET removed_on = NULL, removal_reason = NULL, removal_outcome = NULL, removal_session_id = NULL
                WHERE user_id = ? AND removal_session_id = ?', [$uid, $wsId]);
            foreach (Db::all('SELECT * FROM component_dispositions WHERE user_id = ? AND work_session_id = ? ORDER BY id DESC', [$uid, $wsId]) as $d) {
                if (in_array((int)$d['component_id'], $created, true)) {
                    continue;
                }
                $prev = $d['previous_disposition'] ?: 'STORED';
                $active = !in_array($prev, ['RETIRED', 'DISCARDED', 'SOLD', 'WARRANTY_RETURN'], true);
                Db::run("UPDATE components SET disposition = ?, status = ?, retired_on = IF(? = 'ACTIVE', NULL, retired_on), updated_at = ? WHERE id = ? AND user_id = ?",
                    [$prev, $active ? 'ACTIVE' : 'RETIRED', $active ? 'ACTIVE' : 'RETIRED', $now, $d['component_id'], $uid]);
            }
            Db::run('DELETE FROM component_dispositions WHERE user_id = ? AND work_session_id = ?', [$uid, $wsId]);
            Db::run('UPDATE maintenance_events SET voided_at = ?, void_reason = ? WHERE user_id = ? AND work_session_id = ? AND voided_at IS NULL', [$now, 'undone', $uid, $wsId]);
            Db::run('UPDATE consumable_txns SET voided_at = ? WHERE user_id = ? AND work_session_id = ? AND voided_at IS NULL', [$now, $uid, $wsId]);
            Db::run('UPDATE journal_entries SET repair = NULL, repair_text = NULL, repaired_on = NULL, repair_session_id = NULL WHERE user_id = ? AND repair_session_id = ?', [$uid, $wsId]);
            if ($created) {
                $in = implode(',', $created);
                Db::run("DELETE FROM installations WHERE user_id = ? AND component_id IN ($in)", [$uid]);
                Db::run("DELETE FROM components WHERE user_id = ? AND id IN ($in)", [$uid]);
            }
            Db::run("UPDATE service_orders SET status = 'VOIDED' WHERE user_id = ? AND send_session_id = ?", [$uid, $wsId]);
            Db::run("UPDATE service_orders SET status = 'OUT', returned_on = NULL, outcome = NULL, cost_cents = NULL, receipt_ref = NULL, return_notes = NULL,
                return_session_id = NULL, event_id = NULL, replacement_id = NULL WHERE user_id = ? AND return_session_id = ?", [$uid, $wsId]);
            Db::run('UPDATE purchase_bundles SET voided_at = ?, void_reason = ? WHERE user_id = ? AND work_session_id = ? AND voided_at IS NULL', [$now, 'undone', $uid, $wsId]);
            Db::run('UPDATE work_sessions SET undone_at = ? WHERE id = ?', [$now, $wsId]);
            ChangeLog::note($uid, 'data', $wsId, 'Undone: ' . $ws['title'] . ($created ? ' (' . count($created) . ' parts it added are gone)' : ''));
        });
    }

    // ------------------------------------------------------------------ frame and wheels always exist

    /** Every bike has its frame (with fork) as a part, so a frame swap keeps km and history with the frame. */
    public static function ensureFrame(int $uid, int $bikeId): void
    {
        $bike = Domain::bike($uid, $bikeId);
        $has = Db::one("SELECT i.id, i.installed_on, i.note FROM installations i JOIN components c ON c.id = i.component_id
            WHERE i.user_id = ? AND i.bike_id = ? AND c.component_type = 'FRAME' AND i.voided_at IS NULL ORDER BY i.installed_on LIMIT 1", [$uid, $bikeId]);
        $firstRide = Db::value('SELECT MIN(ride_date) FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL', [$uid, $bikeId]);
        $start = min(array_filter([$bike['purchase_date'], $firstRide, today()]));
        if (!$has) {
            $cid = self::createComponent($uid, ['component_type' => 'FRAME', 'label' => $bike['name'] . ' frame',
                'maker' => $bike['maker'], 'model' => $bike['model'], 'prior_usage' => 'NEW', 'purchase_date' => $bike['purchase_date'],
                'notes' => self::AUTO_FRAME_NOTE]);
            Db::insert('installations', ['user_id' => $uid, 'component_id' => $cid, 'bike_id' => $bikeId, 'slot' => 'FRAME',
                'installed_on' => $start, 'note' => self::AUTO_FRAME_NOTE, 'created_at' => now_utc()]);
        } elseif ($has['note'] === self::AUTO_FRAME_NOTE && $start < $has['installed_on']) {
            // a ride logged before the frame's first day: the original frame was there
            Db::run('UPDATE installations SET installed_on = ? WHERE id = ?', [$start, $has['id']]);
        }
    }

    /** A wheelset has a front and a rear wheel: add the missing wheel records inside it. */
    public static function ensureWheels(int $uid, int $wheelsetId, ?string $from = null, ?int $ws = null): int
    {
        $set = Domain::component($uid, $wheelsetId);
        if ($set['component_type'] !== 'WHEELSET') {
            return 0;
        }
        $first = Db::value('SELECT MIN(installed_on) FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL', [$uid, $wheelsetId]);
        $from = min(array_filter([$from, $first, $set['purchase_date'], today()]));
        $added = 0;
        foreach (['FRONT_WHEEL' => 'front wheel', 'REAR_WHEEL' => 'rear wheel'] as $type => $word) {
            if (Db::one('SELECT id FROM installations WHERE user_id = ? AND parent_component_id = ? AND slot = ? AND voided_at IS NULL', [$uid, $wheelsetId, $type])) {
                continue;
            }
            $cid = self::createComponent($uid, ['component_type' => $type, 'label' => $set['label'] . ' ' . $word, 'prior_usage' => $set['prior_usage'],
                'starting_km' => $set['starting_km'], 'purchase_date' => $set['purchase_date'], 'tire_setup' => $set['tire_setup'],
                'notes' => self::AUTO_WHEEL_NOTE, 'work_session_id' => $ws]);
            Db::run('UPDATE components SET starting_km_estimate = ? WHERE id = ?', [$set['starting_km_estimate'], $cid]);
            Db::insert('installations', ['user_id' => $uid, 'component_id' => $cid, 'parent_component_id' => $wheelsetId, 'slot' => $type,
                'installed_on' => $from, 'note' => self::AUTO_WHEEL_NOTE, 'work_session_id' => $ws, 'created_at' => now_utc()]);
            $added++;
        }
        return $added;
    }

    /** The wheel (component) in a bike's FRONT_WHEEL / REAR_WHEEL position today, directly or in a wheelset. */
    public static function wheelOnBike(int $uid, int $bikeId, string $wheelType): ?array
    {
        foreach (Domain::installedOn($uid, $bikeId) as $p) {
            if ($p['component_type'] === $wheelType) {
                return $p;
            }
        }
        return null;
    }

    // ------------------------------------------------------------------ stock

    public static function stockLevel(int $uid, int $consumableId): float
    {
        return (float)Db::value("SELECT COALESCE(SUM(CASE WHEN kind IN ('USE','RETURN') THEN -qty ELSE qty END),0) FROM consumable_txns
            WHERE user_id = ? AND consumable_id = ? AND voided_at IS NULL", [$uid, $consumableId]);
    }

    /** Spare parts kept individually: active, not on anything, stored. */
    public static function individualSpares(int $uid, ?string $type = null): array
    {
        $sql = "SELECT c.* FROM components c WHERE c.user_id = ? AND c.status = 'ACTIVE' AND c.disposition IN ('STORED')
            AND NOT EXISTS (SELECT 1 FROM installations i WHERE i.component_id = c.id AND i.removed_on IS NULL AND i.voided_at IS NULL)";
        $args = [$uid];
        if ($type) {
            $sql .= ' AND c.component_type = ?';
            $args[] = $type;
        }
        return Db::all($sql . ' ORDER BY c.component_type, c.label', $args);
    }

    /** Take one unit of counted stock out as an individual part (same transaction as the stock use). */
    public static function drawFromStock(int $uid, int $consumableId, string $on, ?int $ws = null, ?string $label = null): int
    {
        return Db::tx(function () use ($uid, $consumableId, $on, $ws, $label) {
            $c = Db::one("SELECT * FROM consumables WHERE id = ? AND user_id = ? AND tracking_mode = 'COUNTED' AND component_type IS NOT NULL", [$consumableId, $uid])
                ?? throw new NotFound('Stock line not found.');
            if ((int)$c['track_stock'] && self::stockLevel($uid, $consumableId) < 1) {
                throw new UserError('No ' . $c['name'] . ' left in stock.');
            }
            $p = $c['product_id'] ? Db::one('SELECT * FROM products WHERE id = ?', [$c['product_id']]) : null;
            $cid = self::createComponent($uid, ['component_type' => $c['component_type'], 'product_id' => $c['product_id'],
                'label' => $label ?: $c['name'], 'maker' => $p['maker'] ?? $c['maker'], 'model' => $p['model'] ?? null,
                'prior_usage' => 'NEW', 'purchase_date' => $on, 'notes' => 'Taken from stock: ' . $c['name'], 'work_session_id' => $ws]);
            $txn = Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $consumableId, 'kind' => 'USE', 'qty' => 1, 'happened_on' => $on,
                'note' => 'became part #' . $cid, 'work_session_id' => $ws, 'created_at' => now_utc()]);
            Db::run('UPDATE components SET from_stock_txn_id = ? WHERE id = ?', [$txn, $cid]);
            return $cid;
        });
    }

    /** Spares kept per part type (setting, default 2 tubes and 1 tire): counted stock plus stored spares. */
    public static function spareCheck(int $uid): array
    {
        $out = [];
        foreach (UserSettings::spareMinimums($uid) as $type => $min) {
            if ($min <= 0 || !Catalog::type($type)) {
                continue;
            }
            $inStock = 0;
            foreach (Db::all("SELECT id FROM consumables WHERE user_id = ? AND tracking_mode = 'COUNTED' AND component_type = ? AND track_stock = 1 AND archived_at IS NULL", [$uid, $type]) as $c) {
                $inStock += (int)floor(self::stockLevel($uid, (int)$c['id']));
            }
            $individual = count(self::individualSpares($uid, $type));
            $have = $inStock + $individual;
            $unit = Catalog::raw('stock_units')[$type][0] ?? mb_strtolower(Catalog::typeName($type));
            $out[] = ['component_type' => $type, 'unit' => $unit, 'have' => $have, 'in_stock' => $inStock, 'individual' => $individual,
                'minimum' => $min, 'low' => $have < $min,
                'text' => "$have spare " . ($have === 1 ? $unit : $unit . 's') . ", keep at least $min"];
        }
        return $out;
    }

    /** Suggestions only: spare types below what to keep, and stock lines below their minimum. */
    public static function shoppingList(int $uid): array
    {
        $out = [];
        foreach (Db::all('SELECT * FROM consumables WHERE user_id = ? AND track_stock = 1 AND min_stock IS NOT NULL AND archived_at IS NULL ORDER BY name', [$uid]) as $c) {
            $lvl = self::stockLevel($uid, (int)$c['id']);
            if ($lvl < (float)$c['min_stock']) {
                $need = (float)$c['min_stock'] - $lvl;
                $out[] = ['consumable_id' => (int)$c['id'], 'name' => $c['name'], 'unit' => $c['unit'],
                    'text' => 'Buy ' . fmt_qty($c['tracking_mode'] === 'COUNTED' ? ceil($need) : $need) . ' ' . $c['unit'] . ' of ' . $c['name']
                        . ': ' . fmt_qty($lvl) . ' left, minimum ' . fmt_qty((float)$c['min_stock'])];
            }
        }
        foreach (self::spareCheck($uid) as $s) {
            if ($s['low']) {
                $need = $s['minimum'] - $s['have'];
                $out[] = ['consumable_id' => null, 'name' => 'Spare ' . $s['unit'] . 's', 'unit' => $s['unit'],
                    'text' => "Buy $need " . ($need === 1 ? $s['unit'] : $s['unit'] . 's') . ': ' . $s['text']];
            }
        }
        return $out;
    }
}

function fmt_qty(float $q): string
{
    return rtrim(rtrim(number_format($q, 2, '.', ''), '0'), '.');
}
