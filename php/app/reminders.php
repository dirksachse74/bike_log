<?php
declare(strict_types=1);

// Service reminders. Each reminder explains its numbers ("320 km since last hot wax on 2026-10-01,
// interval 500 km"). Status: OVERDUE (past the interval), SOON (inside the warning margin), UNKNOWN
// (not enough information), OK. A reminder never says a part is safe.
//
// Counting starts at the last logged action that resets the rule. Rides on the same day as that action
// count as after it (the cautious choice: the reminder comes a little early, never late). Without a
// logged action: a part bought NEW counts from its first install; RECORDED counts its starting km too;
// UNKNOWN prior use gives "insufficient information" with the km known so far.

final class Reminders
{
    public const ORDER = ['OVERDUE' => 0, 'SOON' => 1, 'ATTENTION' => 2, 'UNKNOWN' => 3, 'OK' => 4, 'SNOOZED' => 5];

    /** Rules that apply to one part: user type rules, replaced by part rules with the same code. */
    public static function rulesFor(int $uid, array $c): array
    {
        $rules = [];
        foreach (Db::all('SELECT * FROM service_rules WHERE user_id = ? AND component_type = ?', [$uid, $c['component_type']]) as $r) {
            $rules[$r['rule_code']] = $r;
        }
        foreach (Db::all('SELECT * FROM service_rules WHERE user_id = ? AND component_id = ?', [$uid, $c['id']]) as $r) {
            $rules[$r['rule_code']] = $r;
        }
        return array_filter($rules, fn($r) => (int)$r['active'] === 1);
    }

    private static function setupMatches(int $uid, array $rule, array $c, ?array $bike): bool
    {
        $need = $rule['requires_setup'];
        if ($need === null || $need === '') {
            return true;
        }
        if ($need === 'MECHANICAL' || $need === 'ELECTRONIC') {
            return $bike !== null && $bike['shifting'] === $need;
        }
        // tire setup lives on the wheel the part hangs on
        $wheel = self::wheelOf($uid, $c);
        return $wheel !== null && $wheel['tire_setup'] === $need;
    }

    private static function wheelOf(int $uid, array $c): ?array
    {
        if (in_array($c['component_type'], ['FRONT_WHEEL', 'REAR_WHEEL'], true)) {
            return $c;
        }
        $i = Domain::openInstallation($uid, (int)$c['id']);
        if (!$i || !$i['parent_component_id']) {
            return null;
        }
        $p = Db::one('SELECT * FROM components WHERE id = ? AND user_id = ?', [$i['parent_component_id'], $uid]);
        return $p ? self::wheelOf($uid, $p) : null;
    }

    private static function resetActions(array $rule): array
    {
        $a = array_filter(explode(',', (string)$rule['reset_actions']));
        return $a ?: [$rule['action_code']];
    }

    /** All reminders of the user's parts that are on a bike today, plus bike-level rules. */
    public static function forUser(int $uid, ?int $onlyBikeId = null, ?int $onlyComponentId = null): array
    {
        $out = [];
        $comps = Db::all("SELECT * FROM components WHERE user_id = ? AND status = 'ACTIVE'" . ($onlyComponentId ? ' AND id = ' . (int)$onlyComponentId : ''), [$uid]);
        foreach ($comps as $c) {
            $bike = Domain::currentBike($uid, (int)$c['id']);
            if (!$bike || ($onlyBikeId && (int)$bike['id'] !== $onlyBikeId)) {
                continue;
            }
            foreach (self::rulesFor($uid, $c) as $rule) {
                if (!self::setupMatches($uid, $rule, $c, $bike)) {
                    continue;
                }
                $out[] = self::evaluateComponent($uid, $rule, $c, $bike);
            }
            foreach (self::attention($uid, $c, $bike) as $a) {
                $out[] = $a;
            }
        }
        if (!$onlyComponentId) {
            $bikes = Db::all("SELECT * FROM bikes WHERE user_id = ? AND status = 'ACTIVE'" . ($onlyBikeId ? ' AND id = ' . (int)$onlyBikeId : ''), [$uid]);
            $bikeRules = array_filter(Db::all("SELECT * FROM service_rules WHERE user_id = ? AND component_type = 'BIKE' AND active = 1", [$uid]));
            foreach ($bikes as $b) {
                foreach ($bikeRules as $rule) {
                    if ($rule['requires_setup'] && $b['shifting'] !== $rule['requires_setup']) {
                        continue;
                    }
                    $out[] = self::evaluateBike($uid, $rule, $b);
                }
            }
        }
        usort($out, fn($a, $b) => [self::ORDER[$a['status']], -$a['progress']] <=> [self::ORDER[$b['status']], -$b['progress']]);
        return $out;
    }

    private static function lastEvent(int $uid, string $col, int $id, array $actions): ?array
    {
        $in = implode(',', array_fill(0, count($actions), '?'));
        return Db::one("SELECT * FROM maintenance_events WHERE user_id = ? AND $col = ? AND voided_at IS NULL AND action_code IN ($in)
            ORDER BY performed_on DESC, id DESC LIMIT 1", array_merge([$uid, $id], $actions));
    }

    private static function snooze(int $uid, string $col, int $id, string $code): ?array
    {
        return Db::one("SELECT * FROM reminder_snoozes WHERE user_id = ? AND $col = ? AND rule_code = ? AND cleared_at IS NULL ORDER BY id DESC LIMIT 1",
            [$uid, $id, $code]);
    }

    public static function evaluateComponent(int $uid, array $rule, array $c, array $bike): array
    {
        $actions = self::resetActions($rule);
        $last = self::lastEvent($uid, 'component_id', (int)$c['id'], $actions);
        $periods = Domain::bikePeriods($uid, (int)$c['id']);
        $firstInstall = $periods ? $periods[0]['from'] : null;
        $actName = mb_strtolower(Catalog::actionName($rule['action_code']));
        $base = ['kind' => 'rule', 'rule' => $rule, 'component' => $c, 'bike' => $bike, 'last' => $last];

        if ($rule['trigger_kind'] === 'ONCE_AFTER_INSTALL') {
            $open = Domain::openInstallation($uid, (int)$c['id']);
            $since = $open['installed_on'] ?? $firstInstall;
            if ($last && $since && $last['performed_on'] >= $since) {
                return $base + ['status' => 'OK', 'progress' => 0, 'snooze' => null, 'text' => "Done on {$last['performed_on']} after fitting on $since."];
            }
            $used = $since ? Domain::rideUsage($uid, $c, $since)['km'] : 0.0;
            if ($rule['window_max_km'] !== null && $used > (float)$rule['window_max_km']) {
                return $base + ['status' => 'OK', 'progress' => 0, 'snooze' => null, 'text' => 'Fitted on ' . $since . ', ' . km($used)
                    . ' since: taken as done (asked for up to ' . km((float)$rule['window_max_km']) . ' after fitting).'];
            }
            return $base + ['status' => 'OVERDUE', 'progress' => 1, 'snooze' => null, 'text' => 'Fitted on ' . ($since ?? '?') . ' (' . km($used) . " since): $actName once before riding hard."
                . ($rule['notes'] ? ' ' . $rule['notes'] : '')];
        }
        if ($rule['trigger_kind'] === 'PARENT_COUNT') {
            return $base + self::parentCount($uid, $rule, $c) + ['snooze' => null];
        }
        if ($rule['trigger_kind'] === 'CYCLE_WINDOW') {
            $r = self::cycleWindow($uid, $rule, $c, $actName);
            return self::applySnooze($base + $r, self::snooze($uid, 'component_id', (int)$c['id'], $rule['rule_code']), $r['used_km'] ?? 0.0);
        }

        if ($last) {
            $since = $last['performed_on'];
            $usage = Domain::rideUsage($uid, $c, $since);
            $usedKm = $usage['km'];
            $sinceText = "since last $actName on $since";
            $known = true;
        } else {
            $usage = Domain::rideUsage($uid, $c);
            $usedKm = $usage['km'];
            $since = $firstInstall;
            if ($c['prior_usage'] === 'NEW') {
                $sinceText = 'since new (fitted ' . ($firstInstall ?? '?') . "), no $actName logged yet";
                $known = true;
            } elseif ($c['prior_usage'] === 'RECORDED') {
                $usedKm += (float)$c['starting_km'];
                $sinceText = 'in total incl. ' . km((float)$c['starting_km']) . ($c['starting_km_estimate'] ? ' (estimated)' : '') . " from before; no $actName logged yet";
                $known = true;
                $since = null;   // calendar start unknown
            } else {
                $sinceText = "counted since tracking began; earlier use unknown and no $actName logged yet";
                $known = false;
            }
        }
        $topUp = null;
        if ($last && $rule['action_code'] === 'WAX_HOT' && $rule['after_top_up_km'] !== null && $rule['interval_km'] !== null) {
            // after a liquid-wax top-up the hot wax follows after_top_up_km later (top-up at 70 km → due at 270 km)
            $tu = Db::one("SELECT * FROM maintenance_events WHERE user_id = ? AND component_id = ? AND action_code = 'WAX_LIQUID' AND voided_at IS NULL
                AND (performed_on > ? OR (performed_on = ? AND id > ?)) ORDER BY performed_on DESC, id DESC LIMIT 1",
                [$uid, $c['id'], $last['performed_on'], $last['performed_on'], $last['id']]);
            if ($tu) {
                $topAt = $usedKm - Domain::rideUsage($uid, $c, $tu['performed_on'])['km'];
                $rule['interval_km'] = $topAt + (float)$rule['after_top_up_km'];
                $sinceText .= '; liquid wax top-up on ' . $tu['performed_on'] . ' at ' . km($topAt) . ', hot wax ' . km((float)$rule['after_top_up_km']) . ' after it';
                $topUp = ['on' => $tu['performed_on'], 'at_km' => $topAt];
            }
        }
        $r = self::judge($rule, $usedKm, $usage, $since, $known, $sinceText);
        $r['used_km'] = $usedKm;
        $r['top_up'] = $topUp;
        $r['due_km'] = $rule['interval_km'] !== null ? (float)$rule['interval_km'] : null;
        if ($known) {
            self::wetRide($uid, $rule, $c, $last, $r);
        }
        $sn = self::snooze($uid, 'component_id', (int)$c['id'], $rule['rule_code']);
        return self::applySnooze($base + $r, $sn, $usedKm);
    }

    public static function evaluateBike(int $uid, array $rule, array $b): array
    {
        $actions = self::resetActions($rule);
        $last = self::lastEvent($uid, 'bike_id', (int)$b['id'], $actions);
        $actName = mb_strtolower(Catalog::actionName($rule['action_code']));
        $since = $last['performed_on'] ?? null;
        $sql = 'SELECT COALESCE(SUM(distance_km),0) km, COALESCE(SUM(duration_s),0) seconds, COUNT(*) rides, SUM(distance_km IS NULL) missing_distance,
            SUM(duration_s IS NULL) missing_duration, MIN(ride_date) first FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL';
        $args = [$uid, $b['id']];
        if ($since) {
            $sql .= ' AND ride_date >= ?';
            $args[] = $since;
        }
        $u = Db::one($sql, $args);
        $u['km'] = (float)$u['km'];
        $u['seconds'] = (int)$u['seconds'];
        $u['missing_distance'] = (int)$u['missing_distance'];
        $u['missing_duration'] = (int)$u['missing_duration'];
        $sinceText = $since ? "since last $actName on $since" : "of all logged rides; no $actName logged yet";
        // without a logged action, count the calendar from the purchase date or the first ride (an estimate)
        $calendarFrom = $since ?? ($b['purchase_date'] ?: $u['first']);
        $r = self::judge($rule, $u['km'], $u, $calendarFrom, $since !== null, $sinceText);
        $base = ['kind' => 'rule', 'rule' => $rule, 'component' => null, 'bike' => $b, 'last' => $last];
        return self::applySnooze($base + $r, self::snooze($uid, 'bike_id', (int)$b['id'], $rule['rule_code']), $u['km']);
    }

    /** Compare usage with the rule's km / months / hours; the worst dimension wins. */
    private static function judge(array $rule, float $usedKm, array $usage, ?string $since, bool $known, string $sinceText): array
    {
        $parts = [];
        $status = 'OK';
        $progress = 0.0;
        $worse = function (string $s) use (&$status) {
            if (self::ORDER[$s] < self::ORDER[$status]) {
                $status = $s;
            }
        };
        $today = today();
        if ($rule['interval_km'] !== null) {
            $iv = (float)$rule['interval_km'];
            $warn = $rule['warn_km'] !== null ? (float)$rule['warn_km'] : $iv * 0.1;
            $parts[] = number_format($usedKm, 0, '.', ' ') . " km $sinceText (interval " . number_format($iv, 0, '.', ' ') . ' km)';
            $progress = max($progress, $iv > 0 ? $usedKm / $iv : 0);
            if ($usedKm >= $iv) {
                $worse('OVERDUE');
            } elseif ($usedKm >= $iv - $warn) {
                $worse('SOON');
            }
            if ($usage['missing_distance'] > 0) {
                $parts[] = $usage['missing_distance'] . ' ride(s) without distance are not counted';
            }
        }
        if ($rule['interval_months'] !== null) {
            $m = (int)$rule['interval_months'];
            if ($since === null) {
                $parts[] = "every $m months: start date unknown";
                $worse('UNKNOWN');
            } else {
                $due = (new DateTimeImmutable($since))->modify("+$m months")->format('Y-m-d');
                $warnDays = $rule['warn_days'] !== null ? (int)$rule['warn_days'] : 14;
                $soon = (new DateTimeImmutable($due))->modify("-$warnDays days")->format('Y-m-d');
                $days = (int)(new DateTimeImmutable($since))->diff(new DateTimeImmutable($today))->format('%a');
                $parts[] = "$days days since $since (every $m months, due $due)";
                $progress = max($progress, $days / max(1, $m * 30.44));
                if ($today >= $due) {
                    $worse('OVERDUE');
                } elseif ($today >= $soon) {
                    $worse('SOON');
                }
            }
        }
        if ($rule['interval_hours'] !== null) {
            $iv = (float)$rule['interval_hours'];
            $h = $usage['seconds'] / 3600;
            $warn = $rule['warn_hours'] !== null ? (float)$rule['warn_hours'] : $iv * 0.1;
            $parts[] = number_format($h, 1) . ' h ride time (every ' . number_format($iv, 0) . ' h)';
            $progress = max($progress, $iv > 0 ? $h / $iv : 0);
            if ($h >= $iv) {
                $worse('OVERDUE');
            } elseif ($h >= $iv - $warn) {
                $worse('SOON');
            }
            if ($usage['missing_duration'] > 0) {
                $parts[] = $usage['missing_duration'] . ' ride(s) without a duration are not counted';
            }
        }
        if (!$known && $status === 'OK') {
            $status = 'UNKNOWN';
        }
        $text = implode('; ', $parts) . '.';
        if (!$known) {
            $text = 'Insufficient information: ' . $text;
        }
        return ['status' => $status, 'progress' => $progress, 'text' => $text];
    }

    private static function applySnooze(array $r, ?array $sn, float $usedKm): array
    {
        if (!$sn || $r['status'] === 'OK') {
            return $r + ['snooze' => null];
        }
        $byDate = $sn['until_date'] !== null && today() < $sn['until_date'];
        $byKm = $sn['until_km'] !== null && $usedKm < (float)$sn['until_km'];
        if ($byDate || $byKm) {
            $r['snoozed_status'] = $r['status'];
            $r['status'] = 'SNOOZED';
            $r['text'] .= ' Snoozed' . ($byDate ? ' until ' . $sn['until_date'] : '') . ($byKm ? ' until ' . number_format((float)$sn['until_km'], 0) . ' km' : '') . '.';
        }
        return $r + ['snooze' => $sn];
    }

    /** Dates of wet rides that counted for the part after a day (a wax logged on a day covers that day's rides). */
    public static function wetRidesAfter(int $uid, array $c, ?string $after): array
    {
        $out = [];
        foreach (Domain::bikePeriods($uid, (int)$c['id']) as $p) {
            $from = $after !== null ? max((new DateTimeImmutable($after))->modify('+1 day')->format('Y-m-d'), $p['from']) : $p['from'];
            if ($p['to'] !== null && $from >= $p['to']) {
                continue;
            }
            $sql = "SELECT ride_date FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL AND conditions = 'WET' AND ride_date >= ?";
            $args = [$uid, $p['bike_id'], $from];
            if ($p['to'] !== null) {
                $sql .= ' AND ride_date < ?';
                $args[] = $p['to'];
            }
            foreach (Db::all($sql, $args) as $r) {
                $out[] = $r['ride_date'];
            }
        }
        sort($out);
        return $out;
    }

    private static function topUpRuleOn(int $uid, array $c): bool
    {
        foreach (self::rulesFor($uid, $c) as $r) {
            if ($r['action_code'] === 'WAX_LIQUID' && $r['trigger_kind'] === 'CYCLE_WINDOW') {
                return true;
            }
        }
        return false;
    }

    /** A wet ride since the last lube / wax makes a chain-lube rule due; with the top-up rule on, the top-up asks instead. */
    private static function wetRide(int $uid, array $rule, array $c, ?array $last, array &$r): void
    {
        $a = Catalog::action($rule['action_code']);
        if ($c['component_type'] !== 'CHAIN' || !$a || $a['kind'] !== 'LUBRICATE') {
            return;
        }
        if ($rule['action_code'] === 'WAX_HOT' && self::topUpRuleOn($uid, $c)) {
            return;
        }
        $wet = self::wetRidesAfter($uid, $c, $last['performed_on'] ?? null);
        if (!$wet) {
            return;
        }
        if (self::ORDER['OVERDUE'] < self::ORDER[$r['status']]) {
            $r['status'] = 'OVERDUE';
        }
        $n = count($wet);
        $r['wet_rides'] = $n;
        $r['text'] .= " $n wet ride" . ($n !== 1 ? 's' : '') . ' since then (last ' . end($wet) . '): ' . mb_strtolower($a['name']) . ' after riding in the wet.';
    }

    /** One action inside a cycle that starts with another (liquid wax 250–300 km after the hot wax). */
    private static function cycleWindow(int $uid, array $rule, array $c, string $actName): array
    {
        $cycleAct = mb_strtolower(Catalog::actionName((string)$rule['cycle_action_code']));
        $lo = (float)$rule['window_min_km'];
        $hi = (float)$rule['window_max_km'];
        $window = km($lo) . '–' . km($hi) . " after $cycleAct";
        $start = self::lastEvent($uid, 'component_id', (int)$c['id'], [(string)$rule['cycle_action_code']]);
        if (!$start) {
            return ['status' => 'UNKNOWN', 'progress' => 0, 'used_km' => null,
                'text' => "Insufficient information: no $cycleAct recorded for " . Domain::componentName($c) . ", so the $actName window ($window) cannot be placed."];
        }
        $used = Domain::rideUsage($uid, $c, $start['performed_on'])['km'];
        $acts = self::resetActions($rule);
        $in = implode(',', array_fill(0, count($acts), '?'));
        $done = Db::all("SELECT * FROM maintenance_events WHERE user_id = ? AND component_id = ? AND voided_at IS NULL AND action_code IN ($in)
            AND (performed_on > ? OR (performed_on = ? AND id > ?)) ORDER BY performed_on, id", array_merge([$uid, $c['id']], $acts,
            [$start['performed_on'], $start['performed_on'], $start['id']]));
        if ($rule['action_code'] === 'WAX_LIQUID') {
            // a wet ride on a waxed chain: top up (again) now, whatever the window says
            $lastTop = $done ? end($done) : $start;
            $wet = self::wetRidesAfter($uid, $c, $lastTop['performed_on']);
            if ($wet) {
                $n = count($wet);
                return ['status' => 'OVERDUE', 'progress' => 1, 'used_km' => $used, 'wet_rides' => $n,
                    'text' => 'Top-up recommended: wet ride on ' . end($wet) . ($n > 1 ? " ($n wet rides since the last wax)" : '')
                        . ". Wax washes off in the rain; a $actName after a wet ride keeps the chain running smoothly (" . km($used)
                        . " since $cycleAct on {$start['performed_on']})."];
            }
        }
        if ($done) {
            $d = $done[0];
            $at = $used - Domain::rideUsage($uid, $c, $d['performed_on'])['km'];
            return ['status' => 'OK', 'progress' => 0, 'used_km' => $used,
                'text' => ucfirst($actName) . " done on {$d['performed_on']} (about " . km($at) . " into the cycle that began with $cycleAct on {$start['performed_on']}). Next one in the next cycle."];
        }
        $head = km($used) . " since $cycleAct on {$start['performed_on']}; one $actName is due $window";
        $warn = $rule['warn_km'] !== null ? (float)$rule['warn_km'] : 0.0;
        if ($used > $hi) {
            [$st, $tail] = ['OVERDUE', ': window passed by ' . km($used - $hi)];
        } elseif ($used >= $lo) {
            [$st, $tail] = ['OVERDUE', ': window is open'];
        } elseif ($used >= $lo - $warn) {
            [$st, $tail] = ['SOON', ': window opens in ' . km($lo - $used)];
        } else {
            [$st, $tail] = ['OK', ': window opens in ' . km($lo - $used)];
        }
        return ['status' => $st, 'progress' => $hi > 0 ? $used / $hi : 0, 'used_km' => $used, 'text' => $head . $tail . '.'];
    }

    /** The parts this part has been mounted on, oldest first (the chains a quick link was on). */
    public static function parentsServed(int $uid, int $componentId): array
    {
        return Db::all('SELECT p.* FROM components p JOIN (SELECT parent_component_id, MIN(installed_on) first FROM installations
            WHERE user_id = ? AND component_id = ? AND voided_at IS NULL AND parent_component_id IS NOT NULL GROUP BY parent_component_id) x
            ON x.parent_component_id = p.id ORDER BY x.first, p.id', [$uid, $componentId]);
    }

    private static function parentCount(int $uid, array $rule, array $c): array
    {
        $parents = self::parentsServed($uid, (int)$c['id']);
        $n = count($parents);
        $limit = max(1, (int)$rule['interval_count']);
        $kind = mb_strtolower(Catalog::typeName(Catalog::parentTypes($c['component_type'])[0] ?? 'part'));
        $names = implode(', ', array_map([Domain::class, 'componentName'], $parents)) ?: 'none yet';
        if ($n > $limit) {
            [$st, $tail] = ['OVERDUE', "replace it (limit $limit)"];
        } elseif ($n === $limit) {
            [$st, $tail] = ['SOON', "replace it at the next $kind change instead of moving it on (limit $limit)"];
        } else {
            $left = $limit - $n;
            [$st, $tail] = ['OK', "can move on to $left more $kind" . ($left !== 1 ? 's' : '')];
        }
        return ['status' => $st, 'progress' => $n / $limit, 'used_count' => $n,
            'text' => "Has been on $n $kind" . ($n !== 1 ? 's' : '') . " ($names): $tail." . ($rule['notes'] ? ' ' . $rule['notes'] : '')];
    }

    /** The latest check of an action came out bad (e.g. chain wear AT_LIMIT) and nothing newer replaced it. */
    private static function attention(int $uid, array $c, array $bike): array
    {
        $out = [];
        $rows = Db::all('SELECT e.* FROM maintenance_events e WHERE e.user_id = ? AND e.component_id = ? AND e.voided_at IS NULL
            AND e.outcome IS NOT NULL AND NOT EXISTS (SELECT 1 FROM maintenance_events l WHERE l.user_id = e.user_id AND l.component_id = e.component_id
            AND l.action_code = e.action_code AND l.voided_at IS NULL AND (l.performed_on > e.performed_on OR (l.performed_on = e.performed_on AND l.id > e.id)))',
            [$uid, $c['id']]);
        foreach ($rows as $e) {
            $a = Catalog::action($e['action_code']);
            if ($a && in_array($e['outcome'], $a['attention_outcomes'], true)) {
                $m = $e['measurement_value'] !== null ? ' (' . rtrim(rtrim((string)$e['measurement_value'], '0'), '.') . ' ' . $e['measurement_unit'] . ')' : '';
                $out[] = ['kind' => 'attention', 'status' => 'ATTENTION', 'progress' => 1, 'rule' => null, 'component' => $c, 'bike' => $bike,
                    'last' => $e, 'snooze' => null,
                    'text' => $a['name'] . ' on ' . $e['performed_on'] . ': ' . Catalog::label($e['outcome']) . $m . '. Stays here until a newer check.'];
            }
        }
        if (in_array($c['component_type'], ['FRONT_WHEEL', 'REAR_WHEEL'], true)) {
            $s = Incidents::spokeInfo($uid, $c);
            if ($s['due']) {
                $out[] = ['kind' => 'attention', 'status' => 'ATTENTION', 'progress' => 1, 'rule' => null, 'component' => $c, 'bike' => $bike,
                    'last' => null, 'snooze' => null, 'name' => 'Broken spokes',
                    'text' => $s['count'] . ' broken spokes since ' . ($s['since'] ? 'the last re-lace (' . $s['since'] . ')' : 'tracking began')
                        . '; from ' . $s['limit'] . ' on, a re-lace is worth considering. Stays here until you log a re-lace or new spokes.'];
            }
        }
        return $out;
    }
}
