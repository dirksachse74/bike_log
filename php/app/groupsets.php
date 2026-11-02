<?php
declare(strict_types=1);

// Groupset import: every part of a groupset in one step (port of services/groupsets.py).
// Templates are data shared with the desktop app (catalog.json → groupset_templates). With a bike, each part
// goes to its position: on the bike, on the wheel fitted there (cassette, rotors) or on another new part
// (chainrings on the crankset). A taken position keeps the old part (new one becomes a spare) or replaces it.
// Everything is one work session, so the whole import can be undone in one step.

final class Groupsets
{
    public const OCCUPIED = ['KEEP' => 'Keep the current part; the new one becomes a spare', 'REPLACE' => 'Replace the current part with the new one'];

    public static function templates(): array
    {
        $out = [];
        foreach (Catalog::raw('groupset_templates') as $t) {
            $out[$t['code']] = $t;
        }
        return $out;
    }

    public static function template(string $code): array
    {
        return self::templates()[$code] ?? throw new UserError('Unknown groupset.');
    }

    /** @return array{0: array, 1: array} chosen values and placeholder variables */
    public static function choose(array $t, array $options): array
    {
        $chosen = [];
        $vars = [];
        foreach ($t['options'] as $o) {
            $v = (string)($options[$o['key']] ?? $o['default']);
            $choice = null;
            foreach ($o['choices'] as $c) {
                if ((string)$c['value'] === $v) {
                    $choice = $c;
                }
            }
            if (!$choice) {
                throw new UserError($o['label'] . ': that choice is not offered.');
            }
            $chosen[$o['key']] = $v;
            $vars += $choice['vars'];
            foreach ($choice['vars'] as $k => $val) {
                $vars[$k] = $val;
            }
        }
        return [$chosen, $vars];
    }

    private static function fill(mixed $v, array $vars): mixed
    {
        if (is_string($v)) {
            return preg_replace_callback('/\{(\w+)\}/', fn($m) => array_key_exists($m[1], $vars) ? (string)$vars[$m[1]] : $m[0], $v);
        }
        if (is_array($v)) {
            return array_map(fn($x) => self::fill($x, $vars), $v);
        }
        return $v;
    }

    public static function items(array $t, array $chosen, array $vars): array
    {
        $out = [];
        foreach ($t['items'] as $it) {
            foreach (($it['when'] ?? []) ?: [] as $k => $vals) {
                if (!in_array($chosen[$k] ?? null, $vals, true)) {
                    continue 2;
                }
            }
            $out[] = ['key' => $it['key'], 'type' => $it['type'], 'name' => self::fill($it['name'], $vars), 'model' => self::fill($it['model'], $vars),
                'specs' => self::fill($it['specs'] ?? [], $vars), 'mount' => $it['mount'], 'default' => $it['default'] ?? true, 'rules' => $it['rules'] ?? []];
        }
        return $out;
    }

    private static function occupant(int $uid, string $col, int $id, string $slot): ?array
    {
        return Db::one("SELECT * FROM installations WHERE user_id = ? AND $col = ? AND slot = ? AND removed_on IS NULL AND voided_at IS NULL", [$uid, $id, $slot]);
    }

    /** What an import would do, item by item, without changing anything. */
    public static function plan(int $uid, string $code, ?int $bikeId, array $options, ?array $include, string $prefix, string $occupied, array $toSpares = []): array
    {
        $t = self::template($code);
        if (!isset(self::OCCUPIED[$occupied])) {
            throw new UserError('Unknown choice for taken positions.');
        }
        $bike = $bikeId ? Domain::bike($uid, $bikeId) : null;
        if ($bike && $bike['status'] !== 'ACTIVE') {
            throw new UserError($bike['name'] . ' is retired.');
        }
        [$chosen, $vars] = self::choose($t, $options);
        $all = self::items($t, $chosen, $vars);
        $keys = array_column($all, 'key');
        $selected = $include === null ? array_values(array_filter($all, fn($i) => $i['default'])) : array_values(array_filter($all, fn($i) => in_array($i['key'], $include, true)));
        if (!$selected) {
            throw new UserError('Pick at least one part to add.');
        }
        $selKeys = array_column($selected, 'key');
        $prefix = trim($prefix) ?: ($t['label_prefix'] ?? $t['series']);
        $taken = [];
        $rows = [];
        foreach ($selected as $it) {
            $m = $it['mount'];
            $row = $it + ['type_name' => Catalog::typeName($it['type']), 'label' => Inventory::uniqueLabel($uid, $it['type'], $prefix . ' ' . $it['name'], $taken),
                'action' => 'SPARE', 'slot' => $m['slot'], 'bike_id' => null, 'parent_key' => null, 'parent_component_id' => null,
                'replaces' => null, 'text' => 'Added as a spare'];
            if (!$bike) {
                $row['text'] = 'Added as a spare (no bike chosen)';
            } elseif (in_array($it['key'], $toSpares, true)) {
                $row['text'] = 'Kept as a spare, not installed (your choice)';
            } elseif (isset($m['parent'])) {
                if (!in_array($m['parent'], $selKeys, true)) {
                    $row['text'] = in_array($m['parent'], $keys, true) ? 'Added as a spare: it goes on a part that is not in this import' : 'Added as a spare';
                } else {
                    $parentLabel = '';
                    foreach ($rows as $r) {
                        if ($r['key'] === $m['parent']) {
                            $parentLabel = $r['label'];
                        }
                    }
                    $row = array_merge($row, ['action' => 'INSTALL', 'parent_key' => $m['parent'], 'text' => 'Mounted on ' . $parentLabel]);
                }
            } else {
                $occ = null;
                $where = $bike['name'];
                if (isset($m['wheel'])) {
                    $wheel = Inventory::wheelOnBike($uid, (int)$bike['id'], $m['wheel']);
                    if (!$wheel) {
                        $row['text'] = 'Added as a spare: ' . $bike['name'] . ' has no ' . mb_strtolower(Catalog::typeName($m['wheel'])) . ' recorded. Install it on the wheel later.';
                        $rows[] = $row;
                        continue;
                    }
                    $row['parent_component_id'] = (int)$wheel['id'];
                    $where = $wheel['label'];
                    $occ = self::occupant($uid, 'parent_component_id', (int)$wheel['id'], $m['slot']);
                } else {
                    $row['bike_id'] = (int)$bike['id'];
                    $occ = self::occupant($uid, 'bike_id', (int)$bike['id'], $m['slot']);
                }
                $slotText = mb_strtolower(Catalog::slotName($m['slot']));
                if (!$occ) {
                    $row = array_merge($row, ['action' => 'INSTALL', 'text' => "Installed on $where ($slotText)"]);
                } else {
                    $old = Domain::component($uid, (int)$occ['component_id']);
                    if ($occupied === 'REPLACE') {
                        $out = Inventory::defaultOutcome($old['component_type']);
                        $row = array_merge($row, ['action' => 'REPLACE', 'replaces' => (int)$old['id'], 'old_outcome' => $out,
                            'text' => 'Replaces ' . $old['label'] . " on $where; " . $old['label'] . ' → ' . mb_strtolower(Inventory::dispositions()[$out] ?? $out)]);
                    } else {
                        $row['text'] = "Added as a spare: $where ($slotText) already has " . $old['label'];
                    }
                }
            }
            $rows[] = $row;
        }
        $counts = ['INSTALL' => 0, 'REPLACE' => 0, 'SPARE' => 0];
        foreach ($rows as $r) {
            $counts[$r['action']]++;
        }
        return ['template' => $t, 'bike' => $bike, 'chosen' => $chosen, 'items' => $rows, 'counts' => $counts, 'all' => $all, 'occupied' => $occupied];
    }

    /** Create the parts from the plan and put them in place, as one work session. */
    public static function import(int $uid, string $code, string $on, ?int $bikeId, array $options, ?array $include, string $prefix,
                                  string $occupied, string $prior, ?string $purchaseDate, array $prices = [], array $toSpares = []): array
    {
        return Db::tx(function () use ($uid, $code, $on, $bikeId, $options, $include, $prefix, $occupied, $prior, $purchaseDate, $prices, $toSpares) {
            $p = self::plan($uid, $code, $bikeId, $options, $include, $prefix, $occupied, $toSpares);
            $t = $p['template'];
            $ws = Inventory::startSession($uid, 'GROUPSET', 'Groupset import: ' . $t['name'], $on);
            $created = [];
            $note = 'Added with the groupset import: ' . $t['name'];
            foreach ($p['items'] as $row) {
                $pid = Inventory::productFor($uid, $row['type'], $t['maker'], $row['model'], $row['specs'], $t['source'],
                    'groupset template ' . $t['code'] . ($t['checked_on'] ? ', ' . $t['checked_on'] : ''),
                    $t['verified'] ? null : "Specs from the groupset template, not verified against the maker's documentation");
                $cid = Inventory::createComponent($uid, ['component_type' => $row['type'], 'label' => $row['label'], 'product_id' => $pid,
                    'maker' => $t['maker'], 'model' => $row['model'], 'prior_usage' => in_array($prior, ['NEW', 'UNKNOWN'], true) ? $prior : 'NEW',
                    'purchase_date' => $purchaseDate ?: $on, 'price_cents' => $prices[$row['key']] ?? null, 'notes' => $note, 'work_session_id' => $ws]);
                $created[$row['key']] = $cid;
                foreach ($row['rules'] as $ruleCode => $fields) {
                    self::componentRule($uid, $cid, $row['type'], $ruleCode, $fields);
                }
                if ($row['action'] === 'INSTALL') {
                    $parent = $row['parent_key'] ? $created[$row['parent_key']] : $row['parent_component_id'];
                    Domain::install($uid, $cid, $parent ? null : $row['bike_id'], $parent ?: null, $row['slot'], $on, null, false, $ws);
                } elseif ($row['action'] === 'REPLACE') {
                    $parent = $row['parent_component_id'];
                    Domain::install($uid, $cid, $parent ? null : $row['bike_id'], $parent ?: null, $row['slot'], $on, null, true, $ws, $row['old_outcome']);
                }
                if ($row['type'] === 'WHEELSET') {
                    Inventory::ensureWheels($uid, $cid, $on, $ws);
                }
            }
            return ['work_session_id' => $ws, 'created' => $created, 'plan' => $p];
        });
    }

    /** A part's own version of a default rule (e.g. AXS batteries: charge every 55 h). */
    private static function componentRule(int $uid, int $cid, string $type, string $code, array $fields): void
    {
        $base = Db::one('SELECT * FROM service_rules WHERE user_id = ? AND component_type = ? AND rule_code = ?', [$uid, $type, $code]);
        if (!$base) {
            return;
        }
        $allowed = ['interval_km', 'interval_months', 'interval_hours', 'warn_km', 'warn_days', 'warn_hours', 'active', 'notes', 'origin', 'name'];
        $row = ['user_id' => $uid, 'rule_code' => $code, 'name' => $base['name'], 'component_id' => $cid, 'action_code' => $base['action_code'],
            'reset_actions' => $base['reset_actions'], 'trigger_kind' => $base['trigger_kind'], 'interval_km' => $base['interval_km'],
            'interval_months' => $base['interval_months'], 'interval_hours' => $base['interval_hours'], 'warn_km' => $base['warn_km'],
            'warn_days' => $base['warn_days'], 'warn_hours' => $base['warn_hours'], 'requires_setup' => $base['requires_setup'],
            'origin' => 'MANUFACTURER', 'active' => $base['active'], 'notes' => $base['notes'], 'created_at' => now_utc(), 'updated_at' => now_utc()];
        foreach ($fields as $k => $v) {
            if (in_array($k, $allowed, true)) {
                $row[$k] = is_bool($v) ? (int)$v : $v;
            }
        }
        Db::insert('service_rules', $row);
    }
}
