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
            $trigger = $r['trigger'];
            $intervalKm = $r['interval_km'];
            $warnKm = $r['warn_km'];
            if ($trigger === 'CYCLE_WINDOW') {
                // liquid-wax window: due at the end of the window, "soon" from its start
                $trigger = 'INTERVAL';
                $intervalKm = $r['window_max_km'];
                $warnKm = $r['window_max_km'] - $r['window_min_km'];
            } elseif ($trigger === 'PARENT_COUNT') {
                continue;   // not in the first PHP release
            }
            if ($trigger === 'INTERVAL' && $intervalKm === null && $r['interval_months'] === null && $r['interval_hours'] === null) {
                continue;
            }
            Db::run('INSERT IGNORE INTO service_rules (user_id, rule_code, name, component_type, action_code, reset_actions, trigger_kind,
                interval_km, interval_months, interval_hours, warn_km, warn_days, warn_hours, requires_setup, origin, active, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
                $userId, $r['rule_code'], $r['name'], $r['component_type'], $r['action_code'], implode(',', $r['reset_actions']),
                $trigger, $intervalKm, $r['interval_months'], $r['interval_hours'], $warnKm, $r['warn_days'], $r['warn_hours'],
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
                $out[] = ['bike_id' => (int)$r['bike_id'], 'from' => $r['installed_on'], 'to' => $r['removed_on'], 'via' => []];
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

    /**
     * Usage of a part from rides (optionally only rides on/after $since, a date).
     * Returns km (known distances), hours, rides, missing_distance, missing_duration.
     */
    public static function rideUsage(int $uid, array $component, ?string $since = null): array
    {
        $acc = ['km' => 0.0, 'seconds' => 0, 'rides' => 0, 'missing_distance' => 0, 'missing_duration' => 0];
        foreach (self::bikePeriods($uid, (int)$component['id']) as $p) {
            $from = $since !== null ? max($since, $p['from']) : $p['from'];
            if ($p['to'] !== null && $from >= $p['to']) {
                continue;
            }
            $sql = 'SELECT COALESCE(SUM(distance_km),0) km, COALESCE(SUM(duration_s),0) s, COUNT(*) n,
                    SUM(distance_km IS NULL) md, SUM(duration_s IS NULL) mt
                    FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL AND ride_date >= ?';
            $args = [$uid, $p['bike_id'], $from];
            if ($p['to'] !== null) {
                $sql .= ' AND ride_date < ?';
                $args[] = $p['to'];
            }
            if (!self::countsIndoor($component, $p)) {
                $sql .= " AND kind = 'OUTDOOR'";
            }
            $r = Db::one($sql, $args);
            $acc['km'] += (float)$r['km'];
            $acc['seconds'] += (int)$r['s'];
            $acc['rides'] += (int)$r['n'];
            $acc['missing_distance'] += (int)$r['md'];
            $acc['missing_duration'] += (int)$r['mt'];
        }
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
    public static function install(int $uid, int $componentId, ?int $bikeId, ?int $parentId, string $slot, string $date, ?string $note = null, bool $replaceOccupant = true): int
    {
        return Db::tx(function () use ($uid, $componentId, $bikeId, $parentId, $slot, $date, $note, $replaceOccupant) {
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
                Db::run('UPDATE installations SET removed_on = ?, removal_reason = ? WHERE id = ?', [$date, 'Moved', $open['id']]);
            }
            $col = $bikeId !== null ? 'bike_id' : 'parent_component_id';
            $target = $bikeId ?? $parentId;
            $occupant = Db::one("SELECT * FROM installations WHERE user_id = ? AND $col = ? AND slot = ? AND removed_on IS NULL AND voided_at IS NULL",
                [$uid, $target, $slot]);
            if ($occupant) {
                if (!$replaceOccupant || $occupant['installed_on'] >= $date) {
                    throw new UserError('That position is taken since ' . $occupant['installed_on'] . '. Remove the part there first.');
                }
                Db::run('UPDATE installations SET removed_on = ?, removal_reason = ? WHERE id = ?', [$date, 'Replaced', $occupant['id']]);
            }
            return Db::insert('installations', [
                'user_id' => $uid, 'component_id' => $componentId, 'bike_id' => $bikeId, 'parent_component_id' => $parentId,
                'slot' => $slot, 'installed_on' => $date, 'note' => $note, 'created_at' => now_utc(),
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
            FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL', [$uid, $bikeId]);
    }

    // ------------------------------------------------------------------ consumables

    public static function stock(int $uid, int $consumableId): float
    {
        return (float)Db::value("SELECT COALESCE(SUM(CASE kind WHEN 'USE' THEN -qty ELSE qty END),0) FROM consumable_txns
            WHERE user_id = ? AND consumable_id = ? AND voided_at IS NULL", [$uid, $consumableId]);
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
            $n = Db::run('UPDATE maintenance_events SET voided_at = ?, void_reason = ? WHERE id = ? AND user_id = ? AND voided_at IS NULL',
                [now_utc(), $reason, $eventId, $uid])->rowCount();
            if ($n !== 1) {
                throw new NotFound('Entry not found.');
            }
            Db::run('UPDATE consumable_txns SET voided_at = ? WHERE maintenance_event_id = ? AND user_id = ?', [now_utc(), $eventId, $uid]);
        });
    }
}
