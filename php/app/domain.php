<?php
declare(strict_types=1);

// Bike rules: installation history, per-part mileage, service reminders with explanations.
// Every function takes the owner's user id and only touches that user's rows.
//
// History rules (same as the desktop app):
// - An installation runs from installed_on (inclusive) to removed_on (exclusive). A ride on the day of a
//   swap counts for the part fitted that day; such rides are flagged so you can check them.
// - Part km = km before tracking (if recorded) + km of rides while the part was on a bike (directly or via
//   a wheel/wheelset) + explicit adjustments. Nothing is cached, so totals are always rebuilt from history.
// - Indoor rides do not count for wheels, tires, tubes, rotors and pads.
// - A ride without a distance is "missing", never zero; it is counted and reported separately.

final class Domain
{
    /** Copy the catalog's default service rules to a new user so intervals can be changed per user. */
    public static function seedUser(int $userId): void
    {
        $now = now_utc();
        foreach (Catalog::defaultRules() as $r) {
            Db::run('INSERT IGNORE INTO service_rules (user_id, rule_code, name, component_type, action_code, reset_actions, trigger_kind,
                interval_km, interval_months, interval_hours, warn_km, warn_days, warn_hours, window_min_km, window_max_km, after_top_up_km,
                cycle_action_code, interval_count, requires_setup, origin, active, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
                $userId, $r['rule_code'], $r['name'], $r['component_type'], $r['action_code'], implode(',', $r['reset_actions']),
                $r['trigger'], $r['interval_km'], $r['interval_months'], $r['interval_hours'], $r['warn_km'], $r['warn_days'], $r['warn_hours'],
                $r['window_min_km'], $r['window_max_km'], $r['after_top_up_km'], $r['cycle_action_code'], $r['interval_count'],
                $r['requires_setup'], $r['origin'], $r['active'] ? 1 : 0, $r['notes'], $now, $now,
            ]);
        }
    }

    // ------------------------------------------------------------------ ownership helpers

    public static function bike(int $uid, int $id): array
    {
        $b = Db::one('SELECT * FROM bikes WHERE id = ? AND user_id = ?', [$id, $uid]);
        if (!$b) {
            throw new NotFound('Bike not found.');
        }
        return $b;
    }

    public static function component(int $uid, int $id): array
    {
        $c = Db::one('SELECT * FROM components WHERE id = ? AND user_id = ?', [$id, $uid]);
        if (!$c) {
            throw new NotFound('Part not found.');
        }
        return $c;
    }

    public static function componentName(array $c): string
    {
        return $c['label'] . ($c['mark'] ? ' [' . $c['mark'] . ']' : '');
    }

    // ------------------------------------------------------------------ installation history

    public static function installations(int $uid, int $componentId): array
    {
        return Db::all('SELECT i.*, b.name AS bike_name, p.label AS parent_label FROM installations i
            LEFT JOIN bikes b ON b.id = i.bike_id LEFT JOIN components p ON p.id = i.parent_component_id
            WHERE i.user_id = ? AND i.component_id = ? ORDER BY i.installed_on, i.id', [$uid, $componentId]);
    }

    public static function openInstallation(int $uid, int $componentId): ?array
    {
        return Db::one('SELECT * FROM installations WHERE user_id = ? AND component_id = ? AND removed_on IS NULL AND voided_at IS NULL',
            [$uid, $componentId]);
    }

    /**
     * Periods in which the part was on a bike: [bike_id, from (incl), to (excl or null), via_parent_types[]].
     * A part on a wheel is on a bike while the wheel is (recursively, max 6 levels).
     */
    public static function bikePeriods(int $uid, int $componentId, int $depth = 0): array
    {
        if ($depth > 6) {
            return [];
        }
        $out = [];
        $rows = Db::all('SELECT i.*, p.component_type AS parent_type FROM installations i LEFT JOIN components p ON p.id = i.parent_component_id
            WHERE i.user_id = ? AND i.component_id = ? AND i.voided_at IS NULL', [$uid, $componentId]);
        foreach ($rows as $r) {
            if ($r['bike_id'] !== null) {
                $out[] = ['bike_id' => (int)$r['bike_id'], 'slot' => $r['slot'], 'from' => $r['installed_on'], 'to' => $r['removed_on'], 'via' => []];
                continue;
            }
            foreach (self::bikePeriods($uid, (int)$r['parent_component_id'], $depth + 1) as $p) {
                $from = max($p['from'], $r['installed_on']);
                $to = self::minEnd($p['to'], $r['removed_on']);
                if ($to === null || $from < $to) {
                    $p['from'] = $from;
                    $p['to'] = $to;
                    $p['via'][] = $r['parent_type'];
                    $out[] = $p;
                }
            }
        }
        usort($out, fn($a, $b) => strcmp($a['from'], $b['from']));
        return $out;
    }

    private static function minEnd(?string $a, ?string $b): ?string
    {
        if ($a === null) {
            return $b;
        }
        if ($b === null) {
            return $a;
        }
        return min($a, $b);
    }

    /** The bike the part is on today (directly or via a wheel), or null. */
    public static function currentBike(int $uid, int $componentId): ?array
    {
        $today = today();
        foreach (self::bikePeriods($uid, $componentId) as $p) {
            if ($p['from'] <= $today && ($p['to'] === null || $p['to'] > $today)) {
                return Db::one('SELECT * FROM bikes WHERE id = ?', [$p['bike_id']]);
            }
        }
        return null;
    }

    public static function countsIndoor(array $component, array $period): bool
    {
        if (in_array($component['component_type'], Catalog::INDOOR_EXCLUDED, true)) {
            return false;
        }
        foreach ($period['via'] as $t) {
            if (in_array($t, Catalog::INDOOR_EXCLUDED, true)) {
                return false;
            }
        }
        return true;
    }

    /** Rides that count at all: not removed, not left out of the km. Use with the table alias r. */
    public const COUNTED = 'r.removed_at IS NULL AND r.excluded_reason IS NULL';

    /** Stands in for the bike of rider gear in reminders. */
    public const RIDER = ['id' => 0, 'name' => 'you (worn)', 'shifting' => null, 'rider' => true];

    /** Worn by the rider today (shoes in use, or cleats on shoes in use). */
    public static function wornNow(int $uid, int $componentId): bool
    {
        $today = today();
        foreach (self::usagePeriods($uid, $componentId) as $p) {
            if ($p['kind'] === 'RIDER' && $p['from'] <= $today && ($p['to'] === null || $p['to'] > $today)) {
                return true;
            }
        }
        return false;
    }

    /** Worn by the rider (shoes): counts every ride while "in use", on any bike. */
    public static function isRiderGear(string $type): bool
    {
        return (bool)(Catalog::type($type)['rider_gear'] ?? false);
    }

    /** Periods in which rider gear was in use: [from, to|null]. */
    public static function riderPeriods(int $uid, int $componentId): array
    {
        $rows = Db::all('SELECT disposition, effective_on FROM component_dispositions WHERE user_id = ? AND component_id = ? ORDER BY effective_on, id',
            [$uid, $componentId]);
        $out = [];
        foreach ($rows as $n => $r) {
            if ($r['disposition'] !== 'IN_USE') {
                continue;
            }
            if (isset($rows[$n + 1]) && $rows[$n + 1]['effective_on'] === $r['effective_on']) {
                continue;   // changed again the same day
            }
            $end = null;
            for ($k = $n + 1; $k < count($rows); $k++) {
                if ($rows[$k]['effective_on'] > $r['effective_on']) {
                    $end = $rows[$k]['effective_on'];
                    break;
                }
            }
            $out[] = [$r['effective_on'], $end];
        }
        return $out;
    }

    /**
     * Every way rides reach a part: fitted on a bike (minus rides that set that position to something else),
     * worn by the rider, or picked for a ride (ride_equipment) - for the part itself and through the parts it
     * hangs on. Each: kind BIKE|RIDER|RIDE, from, to (excl or null), via (parent types), bike_id/slot or root_id.
     */
    public static function usagePeriods(int $uid, int $componentId, int $depth = 0): array
    {
        if ($depth > 6) {
            return [];
        }
        $c = Db::one('SELECT component_type FROM components WHERE id = ? AND user_id = ?', [$componentId, $uid]);
        if (!$c) {
            return [];
        }
        $out = [['kind' => 'RIDE', 'root_id' => $componentId, 'from' => '0001-01-01', 'to' => null, 'via' => []]];
        if (self::isRiderGear($c['component_type'])) {
            foreach (self::riderPeriods($uid, $componentId) as [$from, $to]) {
                $out[] = ['kind' => 'RIDER', 'from' => $from, 'to' => $to, 'via' => []];
            }
        }
        $rows = Db::all('SELECT i.*, p.component_type AS parent_type FROM installations i LEFT JOIN components p ON p.id = i.parent_component_id
            WHERE i.user_id = ? AND i.component_id = ? AND i.voided_at IS NULL', [$uid, $componentId]);
        foreach ($rows as $r) {
            if ($r['bike_id'] !== null) {
                $out[] = ['kind' => 'BIKE', 'bike_id' => (int)$r['bike_id'], 'slot' => $r['slot'], 'from' => $r['installed_on'], 'to' => $r['removed_on'], 'via' => []];
                continue;
            }
            foreach (self::usagePeriods($uid, (int)$r['parent_component_id'], $depth + 1) as $p) {
                $from = max($p['from'], $r['installed_on']);
                $to = self::minEnd($p['to'], $r['removed_on']);
                if ($to === null || $from < $to) {
                    $p['from'] = $from;
                    $p['to'] = $to;
                    $p['via'][] = $r['parent_type'];
                    $out[] = $p;
                }
            }
        }
        return $out;
    }

    /** SQL condition (on rides r) and its arguments for one usage period, from $since on. Null = no rides. */
    public static function periodWhere(int $uid, array $component, array $p, ?string $since = null, ?string $until = null): ?array
    {
        $from = $since !== null ? max($since, $p['from']) : $p['from'];
        $to = $until !== null && ($p['to'] === null || $until < $p['to']) ? $until : $p['to'];
        if ($to !== null && $from >= $to) {
            return null;
        }
        $sql = 'r.user_id = ? AND ' . self::COUNTED . ' AND r.ride_date >= ?';
        $args = [$uid, $from];
        if ($to !== null) {
            $sql .= ' AND r.ride_date < ?';
            $args[] = $to;
        }
        if ($p['kind'] === 'BIKE') {
            $sql .= ' AND r.bike_id = ? AND NOT EXISTS (SELECT 1 FROM ride_equipment e WHERE e.ride_id = r.id AND e.slot = ?)';
            $args[] = $p['bike_id'];
            $args[] = $p['slot'];
        } elseif ($p['kind'] === 'RIDER') {
            $sql .= ' AND r.bike_id IS NOT NULL';
        } else {
            $sql .= ' AND EXISTS (SELECT 1 FROM ride_equipment e WHERE e.ride_id = r.id AND e.component_id = ?)';
            $args[] = $p['root_id'];
        }
        if (!self::countsIndoor($component, $p)) {
            $sql .= " AND r.kind = 'OUTDOOR'";
        }
        return [$sql, $args];
    }

    /**
     * Usage of a part from rides (optionally only rides on/after $since and before $until, dates).
     * Returns km (known distances), hours, rides, missing_distance, missing_duration.
     */
    public static function rideUsage(int $uid, array $component, ?string $since = null, ?string $until = null): array
    {
        $acc = ['km' => 0.0, 'seconds' => 0, 'rides' => 0, 'missing_distance' => 0, 'missing_duration' => 0];
        $parts = [];
        $args = [];
        foreach (self::usagePeriods($uid, (int)$component['id']) as $p) {
            if ($w = self::periodWhere($uid, $component, $p, $since, $until)) {
                $parts[] = '(' . $w[0] . ')';
                array_push($args, ...$w[1]);
            }
        }
        if (!$parts) {
            return $acc;
        }
        // one ride counts once, whichever way it reaches the part
        $r = Db::one('SELECT COALESCE(SUM(r.distance_km),0) km, COALESCE(SUM(r.duration_s),0) s, COUNT(*) n,
            COALESCE(SUM(r.distance_km IS NULL),0) md, COALESCE(SUM(r.duration_s IS NULL),0) mt FROM rides r WHERE ' . implode(' OR ', $parts), $args);
        $acc['km'] = (float)$r['km'];
        $acc['seconds'] = (int)$r['s'];
        $acc['rides'] = (int)$r['n'];
        $acc['missing_distance'] = (int)$r['md'];
        $acc['missing_duration'] = (int)$r['mt'];
        return $acc;
    }

    /** Lifetime km with its sources (known / estimated / missing). */
    public static function totals(int $uid, array $c): array
    {
        $rides = self::rideUsage($uid, $c);
        $adj = Db::one('SELECT COALESCE(SUM(km),0) km, COALESCE(MAX(is_estimate),0) est, COUNT(*) n FROM usage_adjustments
            WHERE user_id = ? AND component_id = ? AND voided_at IS NULL', [$uid, $c['id']]);
        $start = $c['prior_usage'] === 'RECORDED' ? (float)$c['starting_km'] : 0.0;
        $total = $start + $rides['km'] + (float)$adj['km'];
        $estimated = ($c['prior_usage'] === 'RECORDED' && $c['starting_km_estimate']) || $adj['est'];
        $status = $c['prior_usage'] === 'UNKNOWN' ? 'at_least' : ($estimated ? 'estimated' : 'known');
        return [
            'total_km' => $total, 'starting_km' => $start, 'ride_km' => $rides['km'], 'adjust_km' => (float)$adj['km'],
            'hours' => $rides['seconds'] / 3600, 'rides' => $rides['rides'], 'missing_distance' => $rides['missing_distance'],
            'status' => $status,
        ];
    }

    public static function totalsLabel(array $t): string
    {
        $s = km($t['total_km']);
        return match ($t['status']) {
            'at_least' => 'at least ' . $s,
            'estimated' => '≈ ' . $s,
            default => $s,
        };
    }

    /** Parts on a bike on a date (default today), with the slot and what they hang on. */
    public static function installedOn(int $uid, int $bikeId, ?string $date = null): array
    {
        $date ??= today();
        $out = [];
        $walk = function (string $col, int $id, int $depth, ?string $parentLabel) use (&$walk, &$out, $uid, $date) {
            if ($depth > 6) {
                return;
            }
            $rows = Db::all("SELECT i.id AS installation_id, i.slot, i.installed_on, c.* FROM installations i JOIN components c ON c.id = i.component_id
                WHERE i.user_id = ? AND i.$col = ? AND i.voided_at IS NULL AND i.installed_on <= ? AND (i.removed_on IS NULL OR i.removed_on > ?)
                ORDER BY c.component_type, c.label", [$uid, $id, $date, $date]);
            foreach ($rows as $r) {
                $r['depth'] = $depth;
                $r['parent_label'] = $parentLabel;
                $out[] = $r;
                $walk('parent_component_id', (int)$r['id'], $depth + 1, self::componentName($r));
            }
        };
        $walk('bike_id', $bikeId, 0, null);
        return $out;
    }

    /** Install a part on a bike or on another part. If it sits somewhere else, it is moved (removed there that day). */
    public static function install(int $uid, int $componentId, ?int $bikeId, ?int $parentId, string $slot, string $date, ?string $note = null,
                                   bool $replaceOccupant = true, ?int $ws = null, ?string $occupantOutcome = null): int
    {
        return Db::tx(function () use ($uid, $componentId, $bikeId, $parentId, $slot, $date, $note, $replaceOccupant, $ws, $occupantOutcome) {
            $c = self::component($uid, $componentId);
            if ($c['status'] !== 'ACTIVE') {
                throw new UserError('This part is retired. Restore it before installing it.');
            }
            if (($bikeId === null) === ($parentId === null)) {
                throw new UserError('Choose a bike or a part to install it on.');
            }
            if ($bikeId !== null) {
                $b = self::bike($uid, $bikeId);
                if ($b['status'] !== 'ACTIVE') {
                    throw new UserError('This bike is retired.');
                }
            } else {
                $p = self::component($uid, $parentId);
                if (!in_array($p['component_type'], Catalog::parentTypes($c['component_type']), true)) {
                    throw new UserError(Catalog::typeName($c['component_type']) . ' cannot go on a ' . Catalog::typeName($p['component_type']) . '.');
                }
                if (self::isDescendant($uid, $parentId, $componentId)) {
                    throw new UserError('A part cannot be mounted on itself or on a part that hangs on it.');
                }
            }
            if (!in_array($slot, Catalog::slots($c['component_type']), true)) {
                throw new UserError('That position does not fit this part type.');
            }
            // no back-dating into existing history: that is a correction (void the wrong record first)
            $later = Db::one('SELECT id FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL
                AND (installed_on >= ? OR (removed_on IS NOT NULL AND removed_on > ?))', [$uid, $componentId, $date, $date]);
            $open = self::openInstallation($uid, $componentId);
            if ($later && (!$open || (int)$later['id'] !== (int)$open['id'] || $open['installed_on'] >= $date)) {
                throw new UserError('This part already has history on or after ' . $date . '. Correct that record first (Void) or pick a later date.');
            }
            if ($open) {
                Db::run("UPDATE installations SET removed_on = ?, removal_reason = 'Moved', removal_outcome = 'MOVED', removal_session_id = ? WHERE id = ?",
                    [$date, $ws, $open['id']]);
            }
            $col = $bikeId !== null ? 'bike_id' : 'parent_component_id';
            $target = $bikeId ?? $parentId;
            $occupant = Db::one("SELECT * FROM installations WHERE user_id = ? AND $col = ? AND slot = ? AND removed_on IS NULL AND voided_at IS NULL",
                [$uid, $target, $slot]);
            if ($occupant) {
                if (!$replaceOccupant || $occupant['installed_on'] >= $date) {
                    throw new UserError('That position is taken since ' . $occupant['installed_on'] . '. Remove the part there first.');
                }
                $old = self::component($uid, (int)$occupant['component_id']);
                $outcome = $occupantOutcome ?? Inventory::defaultOutcome($old['component_type']);
                Db::run("UPDATE installations SET removed_on = ?, removal_reason = 'Replaced', removal_outcome = ?, removal_session_id = ? WHERE id = ?",
                    [$date, $outcome, $ws, $occupant['id']]);
                Inventory::setDisposition($uid, (int)$old['id'], $outcome, $date, 'replaced by ' . self::componentName($c), $ws);
            }
            if ($c['disposition'] !== 'STORED') {
                Db::updateOwned('components', $componentId, $uid, ['disposition' => 'STORED', 'updated_at' => now_utc()]);
            }
            return Db::insert('installations', [
                'user_id' => $uid, 'component_id' => $componentId, 'bike_id' => $bikeId, 'parent_component_id' => $parentId,
                'slot' => $slot, 'installed_on' => $date, 'note' => $note, 'work_session_id' => $ws, 'created_at' => now_utc(),
            ]);
        });
    }

    public static function isDescendant(int $uid, int $candidate, int $ancestor, int $depth = 0): bool
    {
        if ($candidate === $ancestor) {
            return true;
        }
        if ($depth > 8) {
            return true;
        }
        $parents = Db::all('SELECT parent_component_id FROM installations WHERE user_id = ? AND component_id = ? AND parent_component_id IS NOT NULL
            AND removed_on IS NULL AND voided_at IS NULL', [$uid, $candidate]);
        foreach ($parents as $p) {
            if (self::isDescendant($uid, (int)$p['parent_component_id'], $ancestor, $depth + 1)) {
                return true;
            }
        }
        return false;
    }

    public static function remove(int $uid, int $installationId, string $date, ?string $reason): void
    {
        $i = Db::one('SELECT * FROM installations WHERE id = ? AND user_id = ? AND voided_at IS NULL', [$installationId, $uid]);
        if (!$i || $i['removed_on'] !== null) {
            throw new UserError('This part is not installed there any more.');
        }
        if ($date <= $i['installed_on']) {
            throw new UserError('The removal date must be after the install date (' . $i['installed_on'] . ').');
        }
        Db::run('UPDATE installations SET removed_on = ?, removal_reason = ? WHERE id = ?', [$date, $reason, $installationId]);
        ChangeLog::note($uid, 'installation', $installationId, 'Taken off on ' . $date . ($reason ? ": $reason" : ''),
            $i['bike_id'] ? (int)$i['bike_id'] : null, (int)$i['component_id']);
    }

    /** A wrong record: kept for the history, left out of all totals. */
    public static function voidInstallation(int $uid, int $installationId, string $reason): void
    {
        if ($reason === '') {
            throw new UserError('Please say why this record is wrong.');
        }
        $n = Db::run('UPDATE installations SET voided_at = ?, void_reason = ? WHERE id = ? AND user_id = ? AND voided_at IS NULL',
            [now_utc(), $reason, $installationId, $uid])->rowCount();
        if ($n !== 1) {
            throw new NotFound('Record not found.');
        }
        $i = Db::one('SELECT bike_id, component_id FROM installations WHERE id = ?', [$installationId]);
        ChangeLog::note($uid, 'installation', $installationId, "Fitting record voided: $reason", $i['bike_id'] ? (int)$i['bike_id'] : null, (int)$i['component_id']);
    }

    public static function retire(int $uid, int $componentId, string $date, ?string $reason): void
    {
        Db::tx(function () use ($uid, $componentId, $date, $reason) {
            self::component($uid, $componentId);
            $open = self::openInstallation($uid, $componentId);
            if ($open) {
                self::remove($uid, (int)$open['id'], $date, $reason ?: 'Retired');
            }
            Db::updateOwned('components', $componentId, $uid, ['status' => 'RETIRED', 'retired_on' => $date, 'retire_reason' => $reason, 'updated_at' => now_utc()]);
        });
    }

    // ------------------------------------------------------------------ rides

    /** Rides that fall on a day when a part was fitted or removed on that bike (check which part they belong to). */
    public static function changeDays(int $uid, int $bikeId): array
    {
        $rows = Db::all('SELECT installed_on d FROM installations WHERE user_id = ? AND bike_id = ? AND voided_at IS NULL
            UNION SELECT removed_on FROM installations WHERE user_id = ? AND bike_id = ? AND voided_at IS NULL AND removed_on IS NOT NULL',
            [$uid, $bikeId, $uid, $bikeId]);
        return array_flip(array_column($rows, 'd'));
    }

    public static function bikeKm(int $uid, int $bikeId): array
    {
        return Db::one('SELECT COALESCE(SUM(distance_km),0) km, COUNT(*) rides, COALESCE(SUM(duration_s),0) s, SUM(distance_km IS NULL) missing
            FROM rides r WHERE r.user_id = ? AND r.bike_id = ? AND ' . self::COUNTED, [$uid, $bikeId]);
    }

    // ------------------------------------------------------------------ consumables

    public static function stock(int $uid, int $consumableId): float
    {
        return Inventory::stockLevel($uid, $consumableId);
    }

    // ------------------------------------------------------------------ maintenance

    public static function logMaintenance(int $uid, array $e): int
    {
        return Db::tx(function () use ($uid, $e) {
            $action = Catalog::action($e['action_code']);
            if (!$action) {
                throw new UserError('Please choose what was done.');
            }
            $type = 'BIKE';
            $bikeId = $e['bike_id'];
            if ($e['component_id']) {
                $c = self::component($uid, $e['component_id']);
                $type = $c['component_type'];
                $bikeId ??= self::currentBike($uid, (int)$c['id'])['id'] ?? null;
            } elseif ($bikeId) {
                self::bike($uid, $bikeId);
            } else {
                throw new UserError('Choose a part or a bike.');
            }
            if (!isset(Catalog::actionsFor($type)[$action['code']])) {
                throw new UserError($action['name'] . ' does not apply to ' . Catalog::typeName($type) . '.');
            }
            $outcome = $e['outcome'] ?: Catalog::outcomeFromMeasurement($action, $e['measurement_value']);
            if ($outcome !== null && $action['outcomes'] && !in_array($outcome, $action['outcomes'], true)) {
                throw new UserError('Unknown result for this action.');
            }
            if ($e['consumable_id']) {
                Db::one('SELECT id FROM consumables WHERE id = ? AND user_id = ?', [$e['consumable_id'], $uid]) ?? throw new NotFound('Supply not found.');
            }
            $id = Db::insert('maintenance_events', [
                'user_id' => $uid, 'action_code' => $action['code'], 'component_id' => $e['component_id'] ?: null, 'bike_id' => $bikeId,
                'performed_on' => $e['performed_on'], 'outcome' => $outcome, 'measurement_value' => $e['measurement_value'],
                'measurement_unit' => $e['measurement_value'] !== null ? ($action['unit'] ?? null) : null,
                'symptom' => isset($e['symptom']) && $e['symptom'] !== '' ? mb_substr((string)$e['symptom'], 0, 500) : null,
                'work_done' => isset($e['work_done']) && $e['work_done'] !== '' ? mb_substr((string)$e['work_done'], 0, 500) : null,
                'consumable_id' => $e['consumable_id'] ?: null, 'consumable_qty' => $e['consumable_qty'],
                'cost_cents' => $e['cost_cents'], 'shop' => $e['shop'], 'notes' => $e['notes'], 'created_at' => now_utc(),
            ]);
            if ($e['consumable_id'] && $e['consumable_qty']) {
                Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $e['consumable_id'], 'kind' => 'USE',
                    'qty' => $e['consumable_qty'], 'happened_on' => $e['performed_on'], 'maintenance_event_id' => $id, 'created_at' => now_utc()]);
            }
            return $id;
        });
    }

    public static function voidMaintenance(int $uid, int $eventId, string $reason): void
    {
        if ($reason === '') {
            throw new UserError('Please say why this entry is wrong.');
        }
        Db::tx(function () use ($uid, $eventId, $reason) {
            $now = now_utc();   // the same moment on the entry and its supplies, so a restore brings back exactly these
            $n = Db::run('UPDATE maintenance_events SET voided_at = ?, void_reason = ? WHERE id = ? AND user_id = ? AND voided_at IS NULL',
                [$now, $reason, $eventId, $uid])->rowCount();
            if ($n !== 1) {
                throw new NotFound('Entry not found.');
            }
            Db::run('UPDATE consumable_txns SET voided_at = ? WHERE maintenance_event_id = ? AND user_id = ? AND voided_at IS NULL', [$now, $eventId, $uid]);
            $e = Db::one('SELECT bike_id, component_id, action_code FROM maintenance_events WHERE id = ?', [$eventId]);
            ChangeLog::note($uid, 'work', $eventId, Catalog::actionName($e['action_code']) . " voided: $reason",
                $e['bike_id'] ? (int)$e['bike_id'] : null, $e['component_id'] ? (int)$e['component_id'] : null);
        });
    }

    /** Bring back an entry marked as wrong (with the supplies it used). One taken back by an undo of its whole step cannot. */
    public static function restoreMaintenance(int $uid, int $eventId): void
    {
        Db::tx(function () use ($uid, $eventId) {
            $e = Db::one('SELECT * FROM maintenance_events WHERE id = ? AND user_id = ?', [$eventId, $uid]) ?? throw new NotFound('Entry not found.');
            if ($e['voided_at'] === null) {
                return;
            }
            if (str_starts_with((string)$e['void_reason'], 'undone')) {
                throw new UserError('This entry was taken back with Undo of its whole step. Record the work again instead.');
            }
            Db::run('UPDATE consumable_txns SET voided_at = NULL WHERE maintenance_event_id = ? AND user_id = ? AND voided_at = ?', [$eventId, $uid, $e['voided_at']]);
            Db::run('UPDATE maintenance_events SET voided_at = NULL, void_reason = NULL WHERE id = ?', [$eventId]);
            ChangeLog::note($uid, 'work', $eventId, Catalog::actionName($e['action_code']) . ' restored',
                $e['bike_id'] ? (int)$e['bike_id'] : null, $e['component_id'] ? (int)$e['component_id'] : null);
        });
    }
}
