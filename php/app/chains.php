<?php
declare(strict_types=1);

// Chain rotation and the wax cycle (port of services/chains.py and maintenance.chain_row). Several chains
// (Chain A, Chain B ...) take turns on one bike. One is on the bike; the others are stored "waxed, ready"
// (hot waxed, 0 km since) or "dirty". The hot-wax reminder of the chain on the bike decides when to swap.
// Only the rotation membership (components.rotation_bike_id) is stored; states come from the wax and wear
// events and the installations. Dates only: a wax logged on a day counts that day's later rides as after it.

final class Chains
{
    public const READY = 'READY_TO_INSTALL';
    public const DIRTY = ['NEEDS_HOT_WAX', 'NEW_UNWAXED', 'UNKNOWN'];
    public const STATES = ['INSTALLED' => 'On the bike', 'READY_TO_INSTALL' => 'Waxed, ready', 'NEEDS_HOT_WAX' => 'Needs hot wax',
        'NEW_UNWAXED' => 'New, not waxed yet', 'UNKNOWN' => 'No hot wax recorded', 'WORN' => 'Worn out', 'AWAITING_SERVICE' => 'Waiting for repair',
        'RETIRED' => 'Retired'];

    private static function lastEvent(int $uid, int $cid, string $action): ?array
    {
        return Db::one('SELECT * FROM maintenance_events WHERE user_id = ? AND component_id = ? AND action_code = ? AND voided_at IS NULL
            ORDER BY performed_on DESC, id DESC LIMIT 1', [$uid, $cid, $action]);
    }

    /** One chain's state for the rotation and the chain list. */
    public static function row(int $uid, array $c): array
    {
        $bike = Domain::currentBike($uid, (int)$c['id']);
        $open = Domain::openInstallation($uid, (int)$c['id']);
        $hot = self::lastEvent($uid, (int)$c['id'], 'WAX_HOT');
        $sinceHot = $hot ? Domain::rideUsage($uid, $c, $hot['performed_on'])['km'] : null;
        $wear = self::lastEvent($uid, (int)$c['id'], 'CHAIN_MEASURE_WEAR');
        $worn = $wear && $wear['outcome'] === 'AT_LIMIT';
        if ($c['status'] === 'RETIRED') {
            [$state, $text] = ['RETIRED', 'Retired' . ($c['retired_on'] ? ' on ' . $c['retired_on'] : '')];
        } elseif ($open) {
            [$state, $text] = ['INSTALLED', 'On ' . ($bike['name'] ?? 'a part')];
        } elseif ($worn) {
            [$state, $text] = ['WORN', "Wear at limit on {$wear['performed_on']}; do not install"];
        } elseif ($c['disposition'] === 'AWAITING_SERVICE') {
            [$state, $text] = ['AWAITING_SERVICE', 'Awaiting preparation or repair'];
        } elseif ($hot && $sinceHot == 0.0) {
            [$state, $text] = [self::READY, "Hot waxed on {$hot['performed_on']}, 0 km since"];
        } elseif ($hot) {
            [$state, $text] = ['NEEDS_HOT_WAX', km($sinceHot) . " since hot wax on {$hot['performed_on']}"];
        } elseif ($c['prior_usage'] === 'NEW') {
            [$state, $text] = ['NEW_UNWAXED', 'New chain, not hot waxed yet (factory grease)'];
        } else {
            [$state, $text] = ['UNKNOWN', 'No hot wax recorded'];
        }
        $waxes = (int)Db::value("SELECT COUNT(*) FROM maintenance_events WHERE user_id = ? AND component_id = ? AND action_code = 'WAX_HOT' AND voided_at IS NULL", [$uid, $c['id']]);
        return ['component' => $c, 'id' => (int)$c['id'], 'label' => Domain::componentName($c), 'state' => $state, 'text' => $text,
            'lifetime_km' => Domain::totals($uid, $c)['total_km'], 'km_since_hot_wax' => $sinceHot, 'last_hot_wax' => $hot['performed_on'] ?? null,
            'wax_cycles' => $waxes, 'bike_id' => $bike ? (int)$bike['id'] : null, 'open' => $open,
            'last_wear' => $wear ? ['date' => $wear['performed_on'], 'value' => $wear['measurement_value'], 'unit' => $wear['measurement_unit'], 'outcome' => $wear['outcome']] : null];
    }

    /** Chains of a bike's rotation: the one on the bike plus the stored members, by name. */
    private static function members(int $uid, int $bikeId): array
    {
        $out = [];
        foreach (Domain::installedOn($uid, $bikeId) as $p) {
            if ($p['component_type'] === 'CHAIN') {
                $out[(int)$p['id']] = Domain::component($uid, (int)$p['id']);
            }
        }
        foreach (Db::all("SELECT * FROM components WHERE user_id = ? AND component_type = 'CHAIN' AND rotation_bike_id = ? AND status = 'ACTIVE'", [$uid, $bikeId]) as $c) {
            $out[(int)$c['id']] ??= $c;
        }
        uasort($out, fn($a, $b) => strcmp($a['label'], $b['label']));
        return array_values($out);
    }

    private static function lastOff(int $uid, int $cid): string
    {
        return (string)Db::value('SELECT MAX(removed_on) FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL', [$uid, $cid]);
    }

    public static function rotation(int $uid, int $bikeId): array
    {
        $bike = Domain::bike($uid, $bikeId);
        $comps = self::members($uid, $bikeId);
        $rows = array_map(fn($c) => self::row($uid, $c), $comps);
        $on = null;
        foreach ($rows as $r) {
            if ($r['state'] === 'INSTALLED' && $r['bike_id'] === $bikeId) {
                $on = $r;
            }
        }
        $ready = array_values(array_filter($rows, fn($r) => $r['state'] === self::READY));
        usort($ready, fn($a, $b) => strcmp(self::lastOff($uid, $a['id']), self::lastOff($uid, $b['id'])));   // rested longest first
        $dirty = array_values(array_filter($rows, fn($r) => in_array($r['state'], self::DIRTY, true)));
        $wax = null;
        if ($on) {
            foreach (Reminders::forUser($uid, null, $on['id']) as $rem) {
                if (($rem['rule']['action_code'] ?? '') === 'WAX_HOT') {
                    $wax = $rem;
                }
            }
        }
        $prompt = null;
        if ($on && $wax && in_array($wax['status'], ['SOON', 'OVERDUE'], true)) {
            $kmTxt = $on['km_since_hot_wax'] !== null ? km($on['km_since_hot_wax']) . ' since hot wax' : 'no hot wax recorded';
            if ($ready) {
                $prompt = ['kind' => 'SWAP', 'to' => $ready[0]['id'], 'text' => "{$on['label']} has $kmTxt. Swap to {$ready[0]['label']} (waxed, ready)."];
            } else {
                $names = array_merge(array_column($dirty, 'label'), [$on['label']]);
                $prompt = ['kind' => 'WAX', 'text' => "{$on['label']} has $kmTxt and no waxed chain is ready. Wax " . implode(', ', $names) . ', then put one on.'];
            }
        } elseif (!$on && $ready) {
            $prompt = ['kind' => 'INSTALL', 'to' => $ready[0]['id'], 'text' => "No chain on {$bike['name']}. Put {$ready[0]['label']} on (waxed, ready)."];
        }
        $dirtyIds = array_column($dirty, 'id');
        if ($on && $on['km_since_hot_wax'] !== 0.0) {
            $dirtyIds[] = $on['id'];
        }
        return ['bike' => $bike, 'chains' => $rows, 'on' => $on, 'wax' => $wax, 'ready' => $ready, 'dirty' => $dirtyIds, 'prompt' => $prompt,
            'timeline' => self::timeline($uid, $bikeId, array_column($rows, 'id')), 'candidates' => self::candidates($uid, $bikeId)];
    }

    /** Chains that could join the rotation: chains on no bike (also from another rotation) and counted chain stock. */
    public static function candidates(int $uid, int $bikeId): array
    {
        $out = [];
        foreach (Db::all("SELECT c.*, b.name AS rot_bike FROM components c LEFT JOIN bikes b ON b.id = c.rotation_bike_id WHERE c.user_id = ? AND c.component_type = 'CHAIN'
            AND c.status = 'ACTIVE' AND (c.rotation_bike_id IS NULL OR c.rotation_bike_id <> ?) ORDER BY c.label", [$uid, $bikeId]) as $c) {
            if (Domain::openInstallation($uid, (int)$c['id'])) {
                continue;
            }
            $out['c:' . $c['id']] = Domain::componentName($c) . ($c['rot_bike'] ? ' (in the rotation of ' . $c['rot_bike'] . ', moves here)' : '');
        }
        foreach (Db::all("SELECT * FROM consumables WHERE user_id = ? AND component_type = 'CHAIN' AND tracking_mode = 'COUNTED' AND archived_at IS NULL ORDER BY name", [$uid]) as $l) {
            $left = Inventory::stockLevel($uid, (int)$l['id']);
            if ($left >= 1) {
                $out['s:' . $l['id']] = $l['name'] . ' (from stock, ' . fmt_qty($left) . ' left)';
            }
        }
        return $out;
    }

    public static function add(int $uid, int $bikeId, string $pick, string $on): array
    {
        return Db::tx(function () use ($uid, $bikeId, $pick, $on) {
            $bike = Domain::bike($uid, $bikeId);
            if (preg_match('/^s:(\d+)$/', $pick, $m)) {
                $line = Db::one('SELECT * FROM consumables WHERE id = ? AND user_id = ?', [(int)$m[1], $uid]) ?? throw new NotFound('Stock line not found.');
                if ($line['component_type'] !== 'CHAIN') {
                    throw new UserError($line['name'] . ' is not a chain.');
                }
                $cid = Inventory::drawFromStock($uid, (int)$line['id'], $on);
            } elseif (preg_match('/^c:(\d+)$/', $pick, $m)) {
                $c = Domain::component($uid, (int)$m[1]);
                if ($c['component_type'] !== 'CHAIN') {
                    throw new UserError($c['label'] . ' is not a chain.');
                }
                if ($c['status'] !== 'ACTIVE') {
                    throw new UserError($c['label'] . ' is retired.');
                }
                $i = Domain::openInstallation($uid, (int)$c['id']);
                if ($i && (int)$i['bike_id'] !== $bikeId) {
                    throw new UserError($c['label'] . ' is on another bike. Take it off first.');
                }
                $cid = (int)$c['id'];
            } else {
                throw new UserError('Pick one chain.');
            }
            Db::updateOwned('components', $cid, $uid, ['rotation_bike_id' => $bikeId, 'updated_at' => now_utc()]);
            $c = Domain::component($uid, $cid);
            return ['id' => $cid, 'text' => Domain::componentName($c) . ' joined the chain rotation of ' . $bike['name'] . '.'];
        });
    }

    public static function leave(int $uid, int $cid): void
    {
        $c = Domain::component($uid, $cid);
        Db::updateOwned('components', $cid, $uid, ['rotation_bike_id' => null, 'updated_at' => now_utc()]);
    }

    /** One click: the chain on the bike comes off (stored, keeps its km), the chosen one goes on. */
    public static function swap(int $uid, int $bikeId, int $toId, string $on, ?int $ws = null): string
    {
        return Db::tx(function () use ($uid, $bikeId, $toId, $on, $ws) {
            $rot = self::rotation($uid, $bikeId);
            $new = Domain::component($uid, $toId);
            if ($new['component_type'] !== 'CHAIN') {
                throw new UserError($new['label'] . ' is not a chain.');
            }
            if ($rot['on'] && $rot['on']['id'] === $toId) {
                throw new UserError(Domain::componentName($new) . ' is already on the bike.');
            }
            Domain::install($uid, $toId, $bikeId, null, 'CHAIN', $on, 'Chain rotation', true, $ws, 'STORED');
            if ($new['rotation_bike_id'] === null) {
                Db::updateOwned('components', $toId, $uid, ['rotation_bike_id' => $bikeId]);
            }
            $old = $rot['on'];
            if ($old) {
                Db::run("UPDATE installations SET removal_reason = 'Chain rotation' WHERE user_id = ? AND component_id = ? AND removed_on = ? AND removal_reason = 'Replaced'",
                    [$uid, $old['id'], $on]);
                if ($old['component']['rotation_bike_id'] === null) {
                    Db::updateOwned('components', $old['id'], $uid, ['rotation_bike_id' => $bikeId]);
                }
            }
            return ($old ? $old['label'] . ' off, ' : '') . Domain::componentName($new) . ' on.';
        });
    }

    /** Hot wax several chains at once; optionally swap one onto the bike first so the chain coming off is waxed too. */
    public static function wax(int $uid, int $bikeId, array $ids, string $on, ?int $consumableId = null, ?float $qty = null, ?int $thenInstall = null): string
    {
        return Db::tx(function () use ($uid, $bikeId, $ids, $on, $consumableId, $qty, $thenInstall) {
            $ids = array_values(array_unique(array_map('intval', $ids)));
            if (!$ids) {
                throw new UserError('Tick the chains you waxed.');
            }
            $names = [];
            foreach ($ids as $cid) {
                $c = Domain::component($uid, $cid);
                if ($c['component_type'] !== 'CHAIN') {
                    throw new UserError('Only chains are hot waxed here.');
                }
                $names[] = Domain::componentName($c);
            }
            $swap = $thenInstall ? self::swap($uid, $bikeId, $thenInstall, $on) : null;
            foreach ($ids as $n => $cid) {
                Domain::logMaintenance($uid, ['action_code' => 'WAX_HOT', 'component_id' => $cid, 'bike_id' => null, 'performed_on' => $on, 'outcome' => null,
                    'measurement_value' => null, 'consumable_id' => $consumableId, 'consumable_qty' => $n === 0 ? $qty : null, 'cost_cents' => null, 'shop' => null,
                    'notes' => count($ids) > 1 ? 'waxed together with ' . (count($ids) - 1) . ' other chain(s)' : null]);
            }
            return 'Hot waxed ' . implode(', ', $names) . '.' . ($swap ? ' ' . $swap : '');
        });
    }

    /** Newest first: each stint of a chain on this bike (with its km) and each hot wax / top-up of a rotation chain. */
    public static function timeline(int $uid, int $bikeId, array $chainIds): array
    {
        $rows = [];
        foreach (Db::all("SELECT i.*, c.label, c.mark FROM installations i JOIN components c ON c.id = i.component_id WHERE i.user_id = ? AND i.bike_id = ?
            AND i.voided_at IS NULL AND c.component_type = 'CHAIN'", [$uid, $bikeId]) as $i) {
            $sql = 'SELECT COALESCE(SUM(distance_km),0) FROM rides r WHERE r.user_id = ? AND r.bike_id = ? AND ' . Domain::COUNTED . ' AND ride_date >= ?';
            $args = [$uid, $bikeId, $i['installed_on']];
            if ($i['removed_on']) {
                $sql .= ' AND ride_date < ?';
                $args[] = $i['removed_on'];
            }
            $rows[] = ['kind' => 'ON', 'date' => $i['installed_on'], 'until' => $i['removed_on'], 'id' => (int)$i['component_id'],
                'label' => Domain::componentName($i), 'km' => (float)Db::value($sql, $args), 'sort' => 1];
        }
        if ($chainIds) {
            $in = implode(',', array_map('intval', $chainIds));
            foreach (Db::all("SELECT e.*, c.label, c.mark FROM maintenance_events e JOIN components c ON c.id = e.component_id WHERE e.user_id = ? AND e.component_id IN ($in)
                AND e.action_code IN ('WAX_HOT','WAX_LIQUID') AND e.voided_at IS NULL", [$uid]) as $e) {
                $rows[] = ['kind' => $e['action_code'] === 'WAX_HOT' ? 'WAX' : 'TOP_UP', 'date' => $e['performed_on'], 'until' => null,
                    'id' => (int)$e['component_id'], 'label' => Domain::componentName($e), 'km' => null, 'sort' => 0];
            }
        }
        usort($rows, fn($a, $b) => [$b['date'], $b['sort']] <=> [$a['date'], $a['sort']]);
        return $rows;
    }

    /**
     * One row per wax application on a chain, newest first: type, product, km into the hot-wax cycle when applied,
     * km and days it was the latest application, what ended it, and on the active row what is due next.
     */
    public static function waxApplications(int $uid, array $c): array
    {
        $events = Db::all("SELECT e.*, s.name AS product FROM maintenance_events e LEFT JOIN consumables s ON s.id = e.consumable_id
            WHERE e.user_id = ? AND e.component_id = ? AND e.action_code IN ('WAX_HOT','WAX_LIQUID') AND e.voided_at IS NULL ORDER BY e.performed_on, e.id", [$uid, $c['id']]);
        $kind = ['WAX_HOT' => 'Hot wax', 'WAX_LIQUID' => 'Liquid wax top-up'];
        $since = fn(string $d) => Domain::rideUsage($uid, $c, $d)['km'];
        $rows = [];
        $lastHot = null;
        foreach ($events as $n => $e) {
            if ($e['action_code'] === 'WAX_HOT') {
                $lastHot = $e['performed_on'];
            }
            $next = $events[$n + 1] ?? null;
            $s = $since($e['performed_on']);
            $ridden = $s - ($next ? $since($next['performed_on']) : 0);
            $at = $lastHot === null ? null : ($e['action_code'] === 'WAX_HOT' ? 0.0 : $since($lastHot) - $s);
            $end = $next['performed_on'] ?? today();
            $rows[] = ['n' => $n + 1, 'date' => $e['performed_on'], 'action_code' => $e['action_code'], 'type' => $kind[$e['action_code']],
                'product' => $e['product'], 'at_km' => $at, 'ridden_km' => $ridden,
                'days_on' => (int)(new DateTimeImmutable($e['performed_on']))->diff(new DateTimeImmutable($end))->format('%a'),
                'active' => $next === null, 'ended_by' => $next ? $kind[$next['action_code']] : null, 'next_due' => null];
        }
        if ($rows) {
            $act = &$rows[count($rows) - 1];
            $parts = [];
            foreach (Reminders::rulesFor($uid, $c) as $r) {
                if ($r['action_code'] === 'WAX_LIQUID' && $r['trigger_kind'] === 'CYCLE_WINDOW' && $act['action_code'] === 'WAX_HOT') {
                    $parts[] = 'Top-up at ' . km((float)$r['window_min_km']) . '–' . km((float)$r['window_max_km']);
                }
            }
            if ($lastHot !== null) {
                foreach (Reminders::forUser($uid, null, (int)$c['id']) as $rem) {
                    if (($rem['rule']['action_code'] ?? '') === 'WAX_HOT' && $rem['rule']['interval_km'] !== null) {
                        $due = $rem['top_up'] ? $rem['top_up']['at_km'] + (float)$rem['rule']['after_top_up_km'] : (float)$rem['rule']['interval_km'];
                        $left = $due - (float)$rem['used_km'];
                        $parts[] = 'Hot wax at ' . km($due) . ' (' . ($left >= 0 ? km($left) . ' left' : km(-$left) . ' over') . ')';
                    }
                }
            }
            $act['next_due'] = $parts ? implode(' · ', $parts) : null;
            unset($act);
        }
        return array_reverse($rows);
    }
}
