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
                return $base + ['status' => 'OK', 'progress' => 0, 'text' => "Done on {$last['performed_on']} after fitting on $since."];
            }
            return $base + ['status' => 'OVERDUE', 'progress' => 1, 'text' => 'Fitted on ' . ($since ?? '?') . "; no $actName logged since."];
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
        $r = self::judge($rule, $usedKm, $usage, $since, $known, $sinceText);
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
        return $out;
    }
}
