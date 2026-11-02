<?php
declare(strict_types=1);

// Journal (notes and issues), ride incidents with what they affected, fixes per affected part, the
// punctures report and broken spokes. Port of services/journal.py, incidents.py, repairs.py, punctures.py,
// spokes.py. Nothing is deleted: entries are voided and can be restored.

final class Journal
{
    public static function add(int $uid, array $f): int
    {
        if (empty($f['bike_id']) && empty($f['component_id'])) {
            throw new UserError('A note belongs to a bike or a part.');
        }
        $text = trim((string)($f['text'] ?? ''));
        if ($text === '') {
            if (empty($f['incident_type'])) {
                throw new UserError('Please write something.');
            }
            $text = Catalog::raw('incident_types')[$f['incident_type']] ?? 'Incident';
        }
        return Db::insert('journal_entries', [
            'user_id' => $uid, 'bike_id' => $f['bike_id'] ?? null, 'component_id' => $f['component_id'] ?? null, 'ride_id' => $f['ride_id'] ?? null,
            'entry_on' => $f['entry_on'], 'kind' => !empty($f['incident_type']) ? 'ISSUE' : ($f['kind'] ?? 'NOTE'), 'text' => $text,
            'resolved_on' => $f['resolved_on'] ?? null, 'incident_type' => $f['incident_type'] ?? null, 'incident_group' => $f['incident_group'] ?? null,
            'affected' => $f['affected'] ?? null, 'created_at' => now_utc(),
        ]);
    }

    /** Notes and issues of a bike (incl. its parts' entries made while on it) or of one part. */
    public static function entries(int $uid, ?int $bikeId, ?int $componentId, bool $withVoided = false): array
    {
        $sql = 'SELECT j.*, c.label AS part_label, b.name AS bike_name FROM journal_entries j LEFT JOIN components c ON c.id = j.component_id
            LEFT JOIN bikes b ON b.id = j.bike_id WHERE j.user_id = ? AND j.incident_type IS NULL';
        $args = [$uid];
        if ($bikeId) {
            $sql .= ' AND j.bike_id = ?';
            $args[] = $bikeId;
        }
        if ($componentId) {
            $sql .= ' AND j.component_id = ?';
            $args[] = $componentId;
        }
        if (!$withVoided) {
            $sql .= ' AND j.voided_at IS NULL';
        }
        return Db::all($sql . ' ORDER BY j.entry_on DESC, j.id DESC LIMIT 300', $args);
    }
}

final class Incidents
{
    public const REMOVED = 'incident removed';

    public static function types(): array
    {
        return Catalog::raw('incident_types');
    }

    public static function ride(int $uid, int $rideId): array
    {
        return Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [$rideId, $uid]) ?? throw new NotFound('Ride not found.');
    }

    /** Parts on the ride's bike that day with the slot path from the bike down. */
    public static function partsOnRide(int $uid, array $ride): array
    {
        if (!$ride['bike_id']) {
            return [];
        }
        $day = $ride['ride_date'];
        $out = [];
        $walk = function (string $col, int $id, array $path, int $depth) use (&$walk, &$out, $uid, $day) {
            if ($depth > 6) {
                return;
            }
            foreach (Db::all("SELECT i.slot, c.* FROM installations i JOIN components c ON c.id = i.component_id WHERE i.user_id = ? AND i.$col = ?
                AND i.voided_at IS NULL AND i.installed_on <= ? AND (i.removed_on IS NULL OR i.removed_on > ?)", [$uid, $id, $day, $day]) as $r) {
                if (isset($out[$r['id']])) {
                    continue;
                }
                $r['slots'] = array_merge($path, [$r['slot']]);
                $out[$r['id']] = $r;
                $walk('parent_component_id', (int)$r['id'], $r['slots'], $depth + 1);
            }
        };
        $walk('bike_id', (int)$ride['bike_id'], [], 0);
        return array_values($out);
    }

    private static function matches(array $opt, array $part): bool
    {
        return in_array($part['component_type'], $opt['types'], true)
            && (!$opt['within'] || array_intersect($part['slots'], $opt['within']));
    }

    /** What this incident type can affect on this ride: key, label, component_id (null = not a part), affected text. */
    public static function choices(int $uid, array $ride, string $type): array
    {
        if (!isset(self::types()[$type])) {
            throw new UserError('Unknown kind of incident.');
        }
        $parts = self::partsOnRide($uid, $ride);
        $bike = ['key' => 'BIKE', 'label' => 'Whole bike', 'component_id' => null, 'affected' => null];
        $opts = Catalog::raw('incident_options')[$type] ?? null;
        if ($opts === null) {
            $out = [$bike];
            foreach ($parts as $p) {
                $out[] = ['key' => 'c' . $p['id'], 'label' => Catalog::typeName($p['component_type']) . ': ' . Domain::componentName($p), 'component_id' => (int)$p['id'], 'affected' => null];
            }
            return $out;
        }
        $noTube = [];
        if ($type === 'FLAT') {
            foreach ($parts as $p) {
                if (in_array($p['component_type'], ['FRONT_WHEEL', 'REAR_WHEEL'], true)) {
                    $setup = $p['tire_setup'] ?: UserSettings::get($uid, 'default_tire_setup');
                    if (in_array($setup, ['TUBELESS', 'TUBULAR'], true)) {
                        $noTube[] = $p['component_type'];
                    }
                }
            }
        }
        $out = [];
        $seen = [];
        foreach ($opts as $o) {
            if (in_array('INNER_TUBE', $o['types'], true) && array_intersect($o['within'], $noTube)) {
                continue;
            }
            if ($o['key'] === 'BIKE') {
                $out[] = ['label' => $o['label']] + $bike;
                continue;
            }
            if (!$o['types']) {
                $out[] = ['key' => $o['key'], 'label' => $o['label'], 'component_id' => null, 'affected' => $o['label']];
                continue;
            }
            $found = false;
            foreach ($parts as $p) {
                if (!isset($seen[$p['id']]) && self::matches($o, $p)) {
                    $seen[$p['id']] = true;
                    $found = true;
                    $out[] = ['key' => 'c' . $p['id'], 'label' => $o['label'] . ': ' . Domain::componentName($p), 'component_id' => (int)$p['id'], 'affected' => null];
                }
            }
            if (!$found) {   // not recorded: the position itself can still be picked
                $out[] = ['key' => $o['key'], 'label' => $o['label'] . ' (not recorded)', 'component_id' => null, 'affected' => $o['label']];
            }
        }
        return $out;
    }

    /** Log one incident with everything it affected. Returns its group id. */
    public static function log(int $uid, int $rideId, string $type, array $keys, ?string $text, ?string $resolvedOn): string
    {
        return Db::tx(function () use ($uid, $rideId, $type, $keys, $text, $resolvedOn) {
            $ride = self::ride($uid, $rideId);
            $opts = [];
            foreach (self::choices($uid, $ride, $type) as $o) {
                $opts[$o['key']] = $o;
            }
            $keys = array_values(array_unique($keys ?: ['BIKE']));
            $group = bin2hex(random_bytes(16));
            foreach ($keys as $k) {
                $o = $opts[$k] ?? throw new UserError('That cannot be affected on this ride.');
                if ($o['component_id'] === null && !$ride['bike_id']) {
                    throw new UserError('This ride has no bike; set the bike first.');
                }
                Journal::add($uid, ['ride_id' => $rideId, 'incident_type' => $type, 'incident_group' => $group, 'component_id' => $o['component_id'],
                    'affected' => $o['affected'], 'bike_id' => $ride['bike_id'], 'entry_on' => $ride['ride_date'], 'text' => $text, 'resolved_on' => $resolvedOn]);
            }
            return $group;
        });
    }

    public static function entries(int $uid, string $group, bool $live = true): array
    {
        $rows = Db::all('SELECT j.*, c.label AS part_label, c.component_type FROM journal_entries j LEFT JOIN components c ON c.id = j.component_id
            WHERE j.user_id = ? AND j.incident_group = ?' . ($live ? ' AND j.voided_at IS NULL' : '') . ' ORDER BY j.id', [$uid, $group]);
        if (!$rows) {
            throw new NotFound('Incident not found.');
        }
        return $rows;
    }

    /** Incidents (one row each, with everything affected), newest first. Filters: ride, bike, part, open only. */
    public static function list(int $uid, array $f = []): array
    {
        $sql = 'SELECT DISTINCT incident_group FROM journal_entries WHERE user_id = ? AND incident_type IS NOT NULL';
        $args = [$uid];
        foreach (['ride_id', 'bike_id', 'component_id', 'incident_type'] as $k) {
            if (!empty($f[$k])) {
                $sql .= " AND $k = ?";
                $args[] = $f[$k];
            }
        }
        $sql .= empty($f['removed']) ? ' AND voided_at IS NULL' : " AND void_reason = '" . self::REMOVED . "'";
        if (!empty($f['open'])) {
            $sql .= ' AND resolved_on IS NULL';
        }
        $out = [];
        foreach (Db::run($sql, $args)->fetchAll(PDO::FETCH_COLUMN) as $g) {
            $rows = Db::all('SELECT j.*, c.label AS part_label, c.mark, c.component_type, b.name AS bike_name, r.name AS ride_name, r.distance_km, r.conditions
                FROM journal_entries j LEFT JOIN components c ON c.id = j.component_id LEFT JOIN bikes b ON b.id = j.bike_id LEFT JOIN rides r ON r.id = j.ride_id
                WHERE j.user_id = ? AND j.incident_group = ? AND ' . (empty($f['removed']) ? 'j.voided_at IS NULL' : 'j.void_reason = ?') . ' ORDER BY j.id',
                empty($f['removed']) ? [$uid, $g] : [$uid, $g, self::REMOVED]);
            if (!$rows) {
                continue;
            }
            $first = $rows[0];
            $out[] = ['group' => $g, 'type' => $first['incident_type'], 'label' => self::types()[$first['incident_type']] ?? $first['incident_type'],
                'on' => $first['entry_on'], 'text' => $first['text'] === (self::types()[$first['incident_type']] ?? '') ? null : $first['text'],
                'resolved_on' => $first['resolved_on'], 'ride_id' => $first['ride_id'], 'ride_name' => $first['ride_name'],
                'bike_id' => $first['bike_id'], 'bike_name' => $first['bike_name'], 'conditions' => $first['conditions'], 'affected' => $rows];
        }
        usort($out, fn($a, $b) => [$a['resolved_on'] !== null, $b['on']] <=> [$b['resolved_on'] !== null, $a['on']]);
        return $out;
    }

    public static function setSolved(int $uid, string $group, ?string $on): void
    {
        self::entries($uid, $group);
        Db::run('UPDATE journal_entries SET resolved_on = ?, updated_at = ? WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [$on, now_utc(), $uid, $group]);
    }

    public static function remove(int $uid, string $group): void
    {
        foreach (self::entries($uid, $group) as $e) {
            if ($e['repair_session_id']) {
                throw new UserError('Undo the fix first (it changed parts or stock).');
            }
        }
        Db::run('UPDATE journal_entries SET voided_at = ?, void_reason = ? WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [now_utc(), self::REMOVED, $uid, $group]);
    }

    public static function restore(int $uid, string $group): void
    {
        $n = Db::run('UPDATE journal_entries SET voided_at = NULL, void_reason = NULL WHERE user_id = ? AND incident_group = ? AND void_reason = ?', [$uid, $group, self::REMOVED])->rowCount();
        if (!$n) {
            throw new UserError('Nothing to restore.');
        }
    }

    /**
     * What was done about one affected entry: REPLACED (by a stored spare, one from stock, or a new part), REPAIRED
     * (a patched tube, an adjusted part) or NONE. A replacement is a work session (undoable). When every affected
     * thing has a fix, the incident is solved on that day.
     */
    public static function fix(int $uid, int $entryId, string $action, string $on, array $src = [], ?string $text = null): void
    {
        Db::tx(function () use ($uid, $entryId, $action, $on, $src, $text) {
            $e = Db::one('SELECT * FROM journal_entries WHERE id = ? AND user_id = ? AND voided_at IS NULL AND incident_group IS NOT NULL', [$entryId, $uid])
                ?? throw new NotFound('Entry not found.');
            if ($e['repair']) {
                throw new UserError('This already has a fix. Undo it first.');
            }
            if ($on < $e['entry_on']) {
                throw new UserError('A fix cannot be before the incident (' . $e['entry_on'] . ').');
            }
            $ws = null;
            $label = $text;
            if ($action === 'REPLACED') {
                $old = $e['component_id'] ? Domain::component($uid, (int)$e['component_id']) : null;
                $ws = Inventory::startSession($uid, 'FIX', 'Fix: ' . (self::types()[$e['incident_type']] ?? 'incident'), $on);
                if ($e['incident_type'] === 'SPOKE') {
                    $wheel = $old ?? throw new UserError('Pick the wheel.');
                    if (($src['kind'] ?? '') === 'stock') {
                        Db::one("SELECT id FROM consumables WHERE id = ? AND user_id = ?", [(int)$src['id'], $uid]) ?? throw new NotFound('Stock line not found.');
                        Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => (int)$src['id'], 'kind' => 'USE', 'qty' => 1, 'happened_on' => $on,
                            'note' => 'broken spoke', 'work_session_id' => $ws, 'created_at' => now_utc()]);
                    }
                    $ev = Domain::logMaintenance($uid, ['action_code' => 'SPOKE_REPLACE', 'component_id' => (int)$wheel['id'], 'bike_id' => null, 'performed_on' => $on,
                        'outcome' => null, 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => 'broken spoke']);
                    Db::run('UPDATE maintenance_events SET work_session_id = ? WHERE id = ?', [$ws, $ev]);
                    $label = $label ?: 'spoke replaced';
                } elseif ($old) {
                    $inst = Domain::openInstallation($uid, (int)$old['id']);
                    if (!$inst) {
                        throw new UserError(Domain::componentName($old) . ' is not installed any more; nothing to replace.');
                    }
                    $newId = self::newPart($uid, $old['component_type'], $src, $on, $ws);
                    $outcome = $src['outcome'] ?? Inventory::defaultOutcome($old['component_type']);
                    Domain::install($uid, $newId, $inst['bike_id'] ? (int)$inst['bike_id'] : null, $inst['parent_component_id'] ? (int)$inst['parent_component_id'] : null,
                        $inst['slot'], $on, 'after: ' . (self::types()[$e['incident_type']] ?? 'incident'), true, $ws, $outcome);
                    $label = $label ?: 'replaced by ' . Domain::componentName(Domain::component($uid, $newId));
                } else {
                    // a position without a recorded part (e.g. "Rear tube"): a stock tube or nothing tracked
                    if (($src['kind'] ?? '') === 'stock') {
                        $line = Db::one('SELECT * FROM consumables WHERE id = ? AND user_id = ?', [(int)$src['id'], $uid]) ?? throw new NotFound('Stock line not found.');
                        Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $line['id'], 'kind' => 'USE', 'qty' => 1, 'happened_on' => $on,
                            'note' => 'fix: ' . $e['affected'], 'work_session_id' => $ws, 'created_at' => now_utc()]);
                        $label = $label ?: 'replaced with ' . $line['name'] . ' from stock';
                    } else {
                        $label = $label ?: 'replaced';
                    }
                }
            } elseif ($action === 'REPAIRED') {
                if ($e['component_id'] && Domain::component($uid, (int)$e['component_id'])['component_type'] === 'INNER_TUBE') {
                    $ws = Inventory::startSession($uid, 'FIX', 'Fix: patched tube', $on);
                    $ev = Domain::logMaintenance($uid, ['action_code' => 'TUBE_PATCH', 'component_id' => (int)$e['component_id'], 'bike_id' => null, 'performed_on' => $on,
                        'outcome' => 'REPAIRED', 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => $text]);
                    Db::run('UPDATE maintenance_events SET work_session_id = ? WHERE id = ?', [$ws, $ev]);
                }
                $label = $label ?: 'repaired';
            } elseif ($action !== 'NONE') {
                throw new UserError('Unknown fix.');
            } else {
                $label = $label ?: 'nothing needed';
            }
            Db::run('UPDATE journal_entries SET repair = ?, repair_text = ?, repaired_on = ?, repair_session_id = ?, updated_at = ? WHERE id = ?',
                [$action, mb_substr((string)$label, 0, 255), $on, $ws, now_utc(), $entryId]);
            $open = (int)Db::value('SELECT COUNT(*) FROM journal_entries WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL AND repair IS NULL', [$uid, $e['incident_group']]);
            if ($open === 0) {
                Db::run('UPDATE journal_entries SET resolved_on = COALESCE(resolved_on, ?) WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [$on, $uid, $e['incident_group']]);
            }
        });
    }

    private static function newPart(int $uid, string $type, array $src, string $on, int $ws): int
    {
        switch ($src['kind'] ?? 'new') {
            case 'spare':
                $c = Domain::component($uid, (int)$src['id']);
                if ($c['component_type'] !== $type || $c['status'] !== 'ACTIVE' || Domain::openInstallation($uid, (int)$c['id'])) {
                    throw new UserError('That spare does not fit or is in use.');
                }
                return (int)$c['id'];
            case 'stock':
                return Inventory::drawFromStock($uid, (int)$src['id'], $on, $ws);
            default:
                $label = trim((string)($src['label'] ?? '')) ?: Catalog::typeName($type);
                return Inventory::createComponent($uid, ['component_type' => $type, 'label' => $label, 'prior_usage' => 'NEW', 'purchase_date' => $on, 'work_session_id' => $ws]);
        }
    }

    public static function undoFix(int $uid, int $entryId): void
    {
        Db::tx(function () use ($uid, $entryId) {
            $e = Db::one('SELECT * FROM journal_entries WHERE id = ? AND user_id = ? AND repair IS NOT NULL', [$entryId, $uid]) ?? throw new NotFound('No fix to undo.');
            if ($e['repair_session_id']) {
                Inventory::undoSession($uid, (int)$e['repair_session_id']);
            }
            Db::run('UPDATE journal_entries SET repair = NULL, repair_text = NULL, repaired_on = NULL, repair_session_id = NULL, resolved_on = NULL, updated_at = ? WHERE id = ?', [now_utc(), $entryId]);
            Db::run('UPDATE journal_entries SET resolved_on = NULL WHERE user_id = ? AND incident_group = ?', [$uid, $e['incident_group']]);
        });
    }

    // ------------------------------------------------------------------ broken spokes

    /** Broken spokes of a wheel since it was laced (a re-lace or new spoke set resets the count). */
    public static function spokeInfo(int $uid, array $wheel): array
    {
        $since = Db::value("SELECT MAX(performed_on) FROM maintenance_events WHERE user_id = ? AND component_id = ? AND action_code = 'WHEEL_RELACE' AND voided_at IS NULL", [$uid, $wheel['id']]);
        $set = Db::value("SELECT MAX(i.installed_on) FROM installations i JOIN components c ON c.id = i.component_id WHERE i.user_id = ? AND i.parent_component_id = ?
            AND c.component_type = 'SPOKES' AND i.voided_at IS NULL AND i.removed_on IS NULL", [$uid, $wheel['id']]);
        $since = ($d = array_filter([$since, $set])) ? max($d) : null;
        $breaks = Db::all("SELECT * FROM journal_entries WHERE user_id = ? AND component_id = ? AND incident_type = 'SPOKE' AND voided_at IS NULL ORDER BY entry_on DESC", [$uid, $wheel['id']]);
        $counted = array_filter($breaks, fn($b) => $since === null || $b['entry_on'] > $since);
        $limit = (int)UserSettings::get($uid, 'spoke_relace_after');
        return ['since' => $since, 'breaks' => $breaks, 'count' => count($counted), 'limit' => $limit, 'due' => $limit > 0 && count($counted) >= $limit];
    }

    public static function logSpoke(int $uid, int $wheelId, string $brokeOn, ?string $note, ?string $replacedOn = null, ?int $stockId = null): string
    {
        return Db::tx(function () use ($uid, $wheelId, $brokeOn, $note, $replacedOn, $stockId) {
            $w = Domain::component($uid, $wheelId);
            if (!in_array($w['component_type'], ['FRONT_WHEEL', 'REAR_WHEEL'], true)) {
                throw new UserError('A broken spoke is logged on a front or rear wheel.');
            }
            $group = bin2hex(random_bytes(16));
            $bike = Domain::currentBike($uid, $wheelId);
            $id = Journal::add($uid, ['component_id' => $wheelId, 'bike_id' => $bike['id'] ?? null, 'incident_type' => 'SPOKE', 'incident_group' => $group,
                'entry_on' => $brokeOn, 'text' => $note]);
            if ($replacedOn) {
                self::fix($uid, $id, 'REPLACED', $replacedOn, $stockId ? ['kind' => 'stock', 'id' => $stockId] : []);
            }
            return $group;
        });
    }

    // ------------------------------------------------------------------ punctures

    /** One row per flat, and per model every tire / tube on its own line with its own km (never summed). */
    public static function punctures(int $uid): array
    {
        $rows = [];
        foreach (self::list($uid, ['incident_type' => 'FLAT']) as $inc) {
            $ride = $inc['ride_id'] ? self::ride($uid, (int)$inc['ride_id']) : null;
            $parts = $ride ? self::partsOnRide($uid, $ride) : [];
            foreach ($inc['affected'] as $a) {
                $wheel = null;
                $kind = null;
                $part = null;
                if ($a['component_id']) {
                    $part = Domain::component($uid, (int)$a['component_id']);
                    $kind = $part['component_type'];
                    foreach ($parts as $p) {
                        if ((int)$p['id'] === (int)$part['id']) {
                            $wheel = in_array('REAR_WHEEL', $p['slots'], true) ? 'Rear' : (in_array('FRONT_WHEEL', $p['slots'], true) ? 'Front' : null);
                        }
                    }
                } else {
                    $wheel = str_starts_with((string)$a['affected'], 'Front') ? 'Front' : (str_starts_with((string)$a['affected'], 'Rear') ? 'Rear' : null);
                    $kind = str_contains(mb_strtolower((string)$a['affected']), 'tube') ? 'INNER_TUBE' : 'TIRE';
                }
                // the tire on that wheel that day (a tube flat still tells which tire it was in)
                $tire = $kind === 'TIRE' ? $part : null;
                if (!$tire && $wheel) {
                    foreach ($parts as $p) {
                        if ($p['component_type'] === 'TIRE' && in_array(strtoupper($wheel) . '_WHEEL', $p['slots'], true)) {
                            $tire = $p;
                        }
                    }
                }
                $rows[] = ['on' => $inc['on'], 'group' => $inc['group'], 'bike' => $inc['bike_name'], 'ride_id' => $inc['ride_id'], 'wheel' => $wheel ?? 'Unknown',
                    'damage' => $kind === 'INNER_TUBE' ? 'Tube' : 'Tire', 'part' => $part, 'tire' => $tire, 'conditions' => $inc['conditions'],
                    'fixed' => $a['repair_text']];
            }
        }
        $byModel = ['TIRE' => [], 'INNER_TUBE' => []];
        $counts = [];
        foreach ($rows as $r) {
            foreach (array_filter([$r['part'], $r['damage'] === 'Tube' ? $r['tire'] : null]) as $p) {
                $counts[$p['component_type']][$p['id']] = ($counts[$p['component_type']][$p['id']] ?? 0) + ($p === $r['part'] ? 1 : 0);
            }
        }
        foreach (['TIRE', 'INNER_TUBE'] as $type) {
            foreach (Db::all("SELECT c.* FROM components c WHERE c.user_id = ? AND c.component_type = ? AND EXISTS (SELECT 1 FROM installations i WHERE i.component_id = c.id AND i.voided_at IS NULL)", [$uid, $type]) as $c) {
                $t = Domain::totals($uid, $c);
                $n = $counts[$type][$c['id']] ?? 0;
                $model = trim(($c['maker'] ?? '') . ' ' . ($c['model'] ?? '')) ?: $c['label'];
                $byModel[$type][$model][] = ['component' => $c, 'km' => $t['total_km'], 'punctures' => $n,
                    'km_per_puncture' => $n ? $t['total_km'] / $n : null, 'in_use' => Domain::openInstallation($uid, (int)$c['id']) !== null];
            }
        }
        return ['rows' => $rows, 'by_model' => $byModel];
    }
}
