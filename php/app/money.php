<?php
declare(strict_types=1);

// What a bike cost (initial + running), purchase bundles, sending a part away for repair, and the part life
// report. Port of services/costs.py, bundles.py, service_orders.py, part_life.py. Nothing here is cached:
// every number is computed from the records.

final class Bundles
{
    public static function get(int $uid, int $id): array
    {
        return Db::one('SELECT * FROM purchase_bundles WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Bundle not found.');
    }

    private static function checkMember(int $uid, array $c, int $bundleId): void
    {
        if ($c['bundle_id'] && (int)$c['bundle_id'] !== $bundleId && Db::one('SELECT id FROM purchase_bundles WHERE id = ? AND voided_at IS NULL', [$c['bundle_id']])) {
            throw new UserError($c['label'] . ' already belongs to another bundle.');
        }
        if ($c['price_cents'] !== null) {
            throw new UserError($c['label'] . ' has its own price (' . money((int)$c['price_cents']) . '). A part is priced either on its own or in a bundle: remove its price first, or leave it out.');
        }
        if ($c['from_stock_txn_id']) {
            throw new UserError($c['label'] . ' came from stock; its cost belongs to that stock purchase.');
        }
    }

    public static function create(int $uid, string $name, array $componentIds, ?string $merchant, ?string $on, ?int $priceCents, ?string $notes, ?int $ws = null): int
    {
        return Db::tx(function () use ($uid, $name, $componentIds, $merchant, $on, $priceCents, $notes, $ws) {
            $name = trim($name);
            if ($name === '') {
                throw new UserError('Give the bundle a name, e.g. "Ultegra Di2 R8100 groupset".');
            }
            if (!$componentIds) {
                throw new UserError('Pick the parts that were bought together.');
            }
            if ($priceCents !== null && $priceCents < 0) {
                throw new UserError('A price cannot be negative.');
            }
            $id = Db::insert('purchase_bundles', ['user_id' => $uid, 'name' => mb_substr($name, 0, 160), 'merchant' => $merchant, 'purchased_on' => $on,
                'price_cents' => $priceCents, 'notes' => $notes, 'work_session_id' => $ws, 'created_at' => now_utc()]);
            self::addMembers($uid, $id, $componentIds);
            return $id;
        });
    }

    public static function addMembers(int $uid, int $id, array $componentIds): void
    {
        $b = self::get($uid, $id);
        if ($b['voided_at']) {
            throw new UserError('This bundle was voided.');
        }
        foreach (array_unique(array_map('intval', $componentIds)) as $cid) {
            $c = Domain::component($uid, $cid);
            self::checkMember($uid, $c, $id);
            Db::run('UPDATE components SET bundle_id = ? WHERE id = ? AND user_id = ?', [$id, $cid, $uid]);
        }
    }

    public static function removeMember(int $uid, int $id, int $cid): void
    {
        self::get($uid, $id);
        $n = Db::run('UPDATE components SET bundle_id = NULL WHERE id = ? AND user_id = ? AND bundle_id = ?', [$cid, $uid, $id])->rowCount();
        if (!$n) {
            throw new UserError('That part is not in this bundle.');
        }
    }

    public static function void(int $uid, int $id, string $reason): void
    {
        if (trim($reason) === '') {
            throw new UserError('Say why this bundle is wrong.');
        }
        self::get($uid, $id);
        Db::run('UPDATE purchase_bundles SET voided_at = ?, void_reason = ? WHERE id = ? AND user_id = ? AND voided_at IS NULL', [now_utc(), $reason, $id, $uid]);
    }

    public static function members(int $uid, int $id): array
    {
        return Db::all('SELECT * FROM components WHERE user_id = ? AND bundle_id = ? ORDER BY component_type, label', [$uid, $id]);
    }

    /** Estimated share per part (information only): by the products' list prices where known, otherwise evenly. */
    public static function shares(array $b, array $comps): array
    {
        if ($b['price_cents'] === null || !$comps) {
            return [];
        }
        $ref = [];
        foreach ($comps as $c) {
            $ref[(int)$c['id']] = $c['product_id'] ? (int)Db::value('SELECT list_price_cents FROM products WHERE id = ?', [$c['product_id']]) ?: null : null;
        }
        $known = array_filter($ref);
        $default = $known ? array_sum($known) / count($known) : 1.0;
        $w = array_map(fn($v) => (float)($v ?: $default), $ref);
        $total = array_sum($w);
        $out = array_map(fn($x) => (int)floor($b['price_cents'] * $x / $total), $w);
        $max = array_search(max($w), $w, true);
        $out[$max] += (int)$b['price_cents'] - array_sum($out);
        return $out;
    }

    /** The bike the bundle counts for: where most of its parts were first installed. */
    public static function bikeOf(array $comps, array $firstBike): ?int
    {
        $votes = [];
        foreach ($comps as $c) {
            $b = $firstBike[(int)$c['id']] ?? null;
            if ($b !== null) {
                $votes[$b] = ($votes[$b] ?? 0) + 1;
            }
        }
        if (!$votes) {
            return null;
        }
        arsort($votes);
        return (int)array_key_first($votes);
    }

    public static function rows(int $uid, bool $withVoided = false): array
    {
        $first = Costs::attribution($uid);
        $out = [];
        foreach (Db::all('SELECT * FROM purchase_bundles WHERE user_id = ?' . ($withVoided ? '' : ' AND voided_at IS NULL') . ' ORDER BY purchased_on DESC, id DESC', [$uid]) as $b) {
            $comps = self::members($uid, (int)$b['id']);
            $bike = self::bikeOf($comps, $first);
            $out[] = $b + ['members' => $comps, 'shares' => self::shares($b, $comps), 'bike_id' => $bike,
                'bike' => $bike ? Db::value('SELECT name FROM bikes WHERE id = ?', [$bike]) : null,
                'in_use' => count(array_filter($comps, fn($c) => Domain::openInstallation($uid, (int)$c['id']) !== null))];
        }
        return $out;
    }

    /** Parts that could join a bundle: no own price, not from stock, not in a live bundle. */
    public static function candidates(int $uid): array
    {
        return Db::all('SELECT c.* FROM components c LEFT JOIN purchase_bundles b ON b.id = c.bundle_id AND b.voided_at IS NULL
            WHERE c.user_id = ? AND c.price_cents IS NULL AND c.from_stock_txn_id IS NULL AND b.id IS NULL ORDER BY c.component_type, c.label', [$uid]);
    }
}

final class Costs
{
    // parts built into a wheel come with the wheelset / wheel; tires, tubes, cassettes and rotors ask for a price
    public const BUILT_INTO_WHEEL = ['FRONT_WHEEL', 'REAR_WHEEL', 'HUB', 'HUB_BEARINGS', 'SPOKES', 'RIM', 'RIM_TAPE'];

    /** The bike a part was first installed on, following the parts it hung on. */
    public static function firstBike(int $uid, int $cid, int $depth = 0): ?int
    {
        $i = Db::one('SELECT * FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL ORDER BY installed_on, id LIMIT 1', [$uid, $cid]);
        if (!$i || $depth > 5) {
            return null;
        }
        if ($i['bike_id']) {
            return (int)$i['bike_id'];
        }
        $p = Db::one('SELECT * FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL AND installed_on <= ?
            AND (removed_on IS NULL OR removed_on > ?) ORDER BY installed_on DESC LIMIT 1', [$uid, $i['parent_component_id'], $i['installed_on'], $i['installed_on']]);
        if (!$p) {
            return self::firstBike($uid, (int)$i['parent_component_id'], $depth + 1);
        }
        return $p['bike_id'] ? (int)$p['bike_id'] : self::firstBike($uid, (int)$p['component_id'], $depth + 1);
    }

    /** @return array<int,?int> component id => first bike */
    public static function attribution(int $uid): array
    {
        $out = [];
        foreach (Db::all('SELECT id FROM components WHERE user_id = ?', [$uid]) as $c) {
            $out[(int)$c['id']] = self::firstBike($uid, (int)$c['id']);
        }
        return $out;
    }

    /** Average price per unit of a stock line (purchases with a cost, minus returns). */
    public static function unitCost(int $uid, int $lineId): ?float
    {
        $r = Db::one("SELECT SUM(CASE kind WHEN 'BUY' THEN cost_cents ELSE -cost_cents END) c, SUM(CASE kind WHEN 'BUY' THEN qty ELSE -qty END) q
            FROM consumable_txns WHERE user_id = ? AND consumable_id = ? AND voided_at IS NULL AND kind IN ('BUY','RETURN') AND cost_cents IS NOT NULL AND qty <> 0", [$uid, $lineId]);
        return $r && (float)$r['q'] > 0 ? (float)$r['c'] / (float)$r['q'] : null;
    }

    private static function inPricedParent(int $uid, int $cid, array $liveBundles, int $depth = 0): bool
    {
        if ($depth > 5) {
            return false;
        }
        foreach (Db::all('SELECT DISTINCT parent_component_id FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL AND parent_component_id IS NOT NULL', [$uid, $cid]) as $r) {
            $p = Db::one('SELECT * FROM components WHERE id = ?', [$r['parent_component_id']]);
            if (!$p) {
                continue;
            }
            if ($p['price_cents'] !== null || isset($liveBundles[(int)$p['bundle_id']]) || self::inPricedParent($uid, (int)$p['id'], $liveBundles, $depth + 1)) {
                return true;
            }
        }
        return false;
    }

    private static function firstFrame(int $uid, int $bikeId): ?array
    {
        return Db::one("SELECT c.* FROM components c JOIN installations i ON i.component_id = c.id WHERE i.user_id = ? AND i.bike_id = ? AND i.voided_at IS NULL
            AND c.component_type = 'FRAME' ORDER BY i.installed_on, i.id LIMIT 1", [$uid, $bikeId]);
    }

    public static function bike(int $uid, int $bikeId, ?array $first = null): array
    {
        $bike = Domain::bike($uid, $bikeId);
        $first ??= self::attribution($uid);
        $original = self::firstFrame($uid, $bikeId);
        $frameInitial = $bike['purchase_price_cents'] === null && $original && $original['price_cents'] !== null && !$original['bundle_id'];
        $items = [];
        $unpriced = [];
        $live = [];
        foreach (Db::all('SELECT * FROM purchase_bundles WHERE user_id = ? AND voided_at IS NULL', [$uid]) as $b) {
            $live[(int)$b['id']] = $b;
        }
        $unpricedBundles = 0;
        foreach ($live as $b) {
            $comps = Bundles::members($uid, (int)$b['id']);
            if (Bundles::bikeOf($comps, $first) !== $bikeId) {
                continue;
            }
            if ($b['price_cents'] === null) {
                $unpricedBundles++;
                continue;
            }
            $items[] = ['kind' => 'BUNDLE', 'date' => $b['purchased_on'], 'text' => $b['name'] . ' (' . count($comps) . ' parts' . ($b['merchant'] ? ', ' . $b['merchant'] : '') . ')',
                'cents' => (int)$b['price_cents'], 'estimated' => false, 'bundle_id' => (int)$b['id'], 'component_id' => null];
        }
        foreach ($first as $cid => $bid) {
            if ($bid !== $bikeId) {
                continue;
            }
            $c = Db::one('SELECT * FROM components WHERE id = ?', [$cid]);
            if (isset($live[(int)$c['bundle_id']]) || ($original && (int)$original['id'] === $cid)) {
                continue;
            }
            if ($c['price_cents'] !== null) {
                $items[] = ['kind' => 'PART', 'date' => $c['purchase_date'], 'text' => Domain::componentName($c), 'component_id' => $cid,
                    'cents' => (int)$c['price_cents'], 'estimated' => false];
            } elseif (!$c['from_stock_txn_id'] && !in_array($c['component_type'], ['FRAME', 'FORK'], true)
                && !(in_array($c['component_type'], self::BUILT_INTO_WHEEL, true) && self::inPricedParent($uid, $cid, $live))) {
                $unpriced[] = Domain::componentName($c);
            }
        }
        $eventIds = [];
        foreach (Db::all('SELECT * FROM maintenance_events WHERE user_id = ? AND bike_id = ? AND voided_at IS NULL', [$uid, $bikeId]) as $e) {
            $eventIds[(int)$e['id']] = true;
            if ($e['cost_cents']) {
                $items[] = ['kind' => 'SERVICE', 'date' => $e['performed_on'], 'text' => Catalog::actionName($e['action_code']) . ($e['shop'] ? ' (' . $e['shop'] . ')' : ''),
                    'cents' => (int)$e['cost_cents'], 'estimated' => false, 'component_id' => $e['component_id']];
            }
        }
        $unit = [];
        $unvalued = 0;
        $drawn = [];
        foreach (Db::all('SELECT id, from_stock_txn_id FROM components WHERE user_id = ? AND from_stock_txn_id IS NOT NULL', [$uid]) as $c) {
            $drawn[(int)$c['from_stock_txn_id']] = (int)$c['id'];
        }
        foreach (Db::all("SELECT t.*, s.name, s.unit FROM consumable_txns t JOIN consumables s ON s.id = t.consumable_id WHERE t.user_id = ? AND t.kind = 'USE' AND t.voided_at IS NULL", [$uid]) as $t) {
            $mine = isset($eventIds[(int)$t['maintenance_event_id']]) || (isset($drawn[(int)$t['id']]) && ($first[$drawn[(int)$t['id']]] ?? null) === $bikeId);
            if (!$mine || !(float)$t['qty']) {
                continue;
            }
            $unit[$t['consumable_id']] ??= self::unitCost($uid, (int)$t['consumable_id']);
            if ($unit[$t['consumable_id']] === null) {
                $unvalued++;
                continue;
            }
            $items[] = ['kind' => 'STOCK', 'date' => $t['happened_on'], 'text' => fmt_qty((float)$t['qty']) . ' ' . $t['unit'] . ' ' . $t['name'],
                'cents' => (int)round($unit[$t['consumable_id']] * (float)$t['qty']), 'estimated' => true];
        }
        $sum = fn(string $k) => array_sum(array_map(fn($i) => $i['cents'], array_filter($items, fn($i) => $i['kind'] === $k)));
        $running = $sum('PART') + $sum('BUNDLE') + $sum('STOCK') + $sum('SERVICE');
        $initial = $frameInitial ? (int)$original['price_cents'] : ($bike['purchase_price_cents'] !== null ? (int)$bike['purchase_price_cents'] : null);
        usort($items, fn($a, $b) => strcmp((string)$b['date'], (string)$a['date']));
        $km = Domain::bikeKm($uid, $bikeId)['km'];
        $total = ($initial ?? 0) + $running;
        return ['initial' => $initial, 'initial_source' => $frameInitial ? 'FRAME' : ($initial !== null ? 'BIKE' : null), 'frame' => $original,
            'parts' => $sum('PART'), 'bundles' => $sum('BUNDLE'), 'stock' => $sum('STOCK'), 'services' => $sum('SERVICE'),
            'running' => $running, 'total' => $total, 'estimated' => (bool)array_filter($items, fn($i) => $i['estimated']),
            'unpriced' => $unpriced, 'unpriced_bundles' => $unpricedBundles, 'unvalued_stock_uses' => $unvalued, 'items' => $items,
            'km' => (float)$km, 'per_km' => $km > 0 && $total > 0 ? (int)round($total / $km) : null];
    }
}

final class ServiceOrders
{
    public const OUTCOMES = ['REPAIRED_PAID' => 'Repaired (paid)', 'REPAIRED_WARRANTY' => 'Repaired under warranty',
        'REPLACED_WARRANTY' => 'Replaced under warranty', 'NOT_REPAIRED' => 'Not repaired'];

    public static function get(int $uid, int $id): array
    {
        return Db::one('SELECT * FROM service_orders WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Service order not found.');
    }

    public static function openFor(int $uid, int $cid): ?array
    {
        return Db::one("SELECT * FROM service_orders WHERE user_id = ? AND component_id = ? AND status = 'OUT'", [$uid, $cid]);
    }

    /** Take the part off (with what was mounted on it) and mark it "awaiting repair"; one undoable step. */
    public static function send(int $uid, int $cid, string $on, ?string $shop, ?string $reason, ?string $group = null): int
    {
        return Db::tx(function () use ($uid, $cid, $on, $shop, $reason, $group) {
            $c = Domain::component($uid, $cid);
            if ($c['status'] === 'RETIRED') {
                throw new UserError($c['label'] . ' is out of use; make it active first.');
            }
            if (self::openFor($uid, $cid)) {
                throw new UserError($c['label'] . ' is already away for repair.');
            }
            if ($group !== null && !Db::one('SELECT id FROM journal_entries WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [$uid, $group])) {
                throw new UserError('That incident does not exist.');
            }
            $bike = Domain::currentBike($uid, $cid);
            $inst = Domain::openInstallation($uid, $cid);
            $ws = Inventory::startSession($uid, 'REPAIR', 'Sent away for repair: ' . Domain::componentName($c) . ($shop ? " ($shop)" : ''), $on);
            $note = 'sent away for repair' . ($shop ? " to $shop" : '');
            if ($inst) {
                Inventory::removeWithOutcome($uid, (int)$inst['id'], $on, 'AWAITING_SERVICE', $note, $ws);
            } else {
                Inventory::setDisposition($uid, $cid, 'AWAITING_SERVICE', $on, $note, $ws);
            }
            return Db::insert('service_orders', ['user_id' => $uid, 'component_id' => $cid, 'bike_id' => $bike['id'] ?? null,
                'from_bike_id' => $inst['bike_id'] ?? null, 'from_parent_id' => $inst['parent_component_id'] ?? null, 'from_slot' => $inst['slot'] ?? null,
                'sent_on' => $on, 'shop' => $shop, 'reason' => $reason, 'incident_group' => $group, 'send_session_id' => $ws, 'status' => 'OUT', 'created_at' => now_utc()]);
        });
    }

    /** What came back; the repaired or new part can go straight back where the old one was. */
    public static function back(int $uid, int $id, string $on, string $outcome, ?int $costCents, ?string $receipt, ?string $notes, bool $putBack = true,
                                string $keepAs = 'STORED', ?string $newLabel = null, ?string $newSerial = null, ?string $newWarranty = null): array
    {
        return Db::tx(function () use ($uid, $id, $on, $outcome, $costCents, $receipt, $notes, $putBack, $keepAs, $newLabel, $newSerial, $newWarranty) {
            $o = self::get($uid, $id);
            if ($o['status'] !== 'OUT') {
                throw new UserError('This part is not away any more.');
            }
            if (!isset(self::OUTCOMES[$outcome])) {
                throw new UserError('What came back? Choose one of: ' . implode(', ', self::OUTCOMES) . '.');
            }
            if ($costCents !== null && $costCents < 0) {
                throw new UserError('The cost cannot be negative.');
            }
            if ($on <= $o['sent_on']) {
                throw new UserError('It was sent away on ' . $o['sent_on'] . '; it must come back later.');
            }
            $c = Domain::component($uid, (int)$o['component_id']);
            $ws = Inventory::startSession($uid, 'REPAIR', 'Back from repair: ' . Domain::componentName($c) . ' (' . mb_strtolower(self::OUTCOMES[$outcome]) . ')', $on);
            $details = implode('; ', array_filter([self::OUTCOMES[$outcome], $o['shop'], $receipt ? "receipt $receipt" : null, $notes]));
            $backId = (int)$c['id'];
            $replacement = null;
            if ($outcome === 'REPLACED_WARRANTY') {
                $taken = [];
                $label = trim((string)$newLabel) ?: Inventory::uniqueLabel($uid, $c['component_type'], $c['label'] . ' (warranty)', $taken);
                $replacement = Inventory::createComponent($uid, ['component_type' => $c['component_type'], 'label' => $label, 'product_id' => $c['product_id'],
                    'maker' => $c['maker'], 'model' => $c['model'], 'prior_usage' => 'NEW', 'purchase_date' => $on,
                    'notes' => 'Warranty replacement for ' . $c['label'], 'work_session_id' => $ws]);
                Db::run('UPDATE components SET serial_number = ?, warranty_until = ? WHERE id = ?', [$newSerial ?: null, $newWarranty ?: null, $replacement]);
                $backId = $replacement;
                [$after, $work] = ['WARRANTY_RETURN', 'replaced under warranty by ' . $label];
            } elseif ($outcome === 'NOT_REPAIRED') {
                if (!in_array($keepAs, ['STORED', 'DISCARDED'], true)) {
                    throw new UserError('Keep it (stored) or discard it.');
                }
                [$after, $work] = [$keepAs, 'not repaired'];
                $putBack = false;
            } else {
                [$after, $work] = ['STORED', 'repaired' . ($outcome === 'REPAIRED_WARRANTY' ? ' under warranty' : '')];
            }
            $ev = Db::insert('maintenance_events', ['user_id' => $uid, 'action_code' => 'REPAIR', 'component_id' => $c['id'], 'bike_id' => $o['bike_id'],
                'performed_on' => $on, 'outcome' => null, 'cost_cents' => $costCents ?: null, 'shop' => $o['shop'], 'notes' => mb_substr($work . '. ' . $details, 0, 1000),
                'work_session_id' => $ws, 'created_at' => now_utc()]);
            Inventory::setDisposition($uid, (int)$c['id'], $after, $on, $work, $ws);
            $placed = $putBack ? self::putBack($uid, $o, $backId, $on, $ws) : null;
            Db::run("UPDATE service_orders SET status = 'BACK', returned_on = ?, outcome = ?, cost_cents = ?, receipt_ref = ?, return_notes = ?,
                return_session_id = ?, event_id = ?, replacement_id = ? WHERE id = ?", [$on, $outcome, $costCents, $receipt, $notes, $ws, $ev, $replacement, $id]);
            $solved = $o['incident_group'] ? self::fixIncident($uid, $o, (int)$c['id'], $outcome, $work, $costCents, $on, $ws) : null;
            return ['work_session_id' => $ws, 'replacement_id' => $replacement, 'placed' => $placed, 'incident_solved' => $solved];
        });
    }

    private static function putBack(int $uid, array $o, int $cid, string $on, int $ws): ?string
    {
        if (!$o['from_slot']) {
            return null;
        }
        if ($o['from_bike_id']) {
            $b = Db::one('SELECT * FROM bikes WHERE id = ? AND user_id = ?', [$o['from_bike_id'], $uid]);
            if (!$b || $b['status'] !== 'ACTIVE') {
                throw new UserError(($b['name'] ?? 'That bike') . ' is retired; untick "put it back".');
            }
        } else {
            $p = Db::one('SELECT * FROM components WHERE id = ? AND user_id = ?', [$o['from_parent_id'], $uid]);
            if (!$p || $p['status'] !== 'ACTIVE') {
                throw new UserError('The part it was mounted on is out of use; untick "put it back".');
            }
        }
        $col = $o['from_bike_id'] ? 'bike_id' : 'parent_component_id';
        $occ = Db::one("SELECT * FROM installations WHERE user_id = ? AND $col = ? AND slot = ? AND removed_on IS NULL AND voided_at IS NULL",
            [$uid, $o['from_bike_id'] ?: $o['from_parent_id'], $o['from_slot']]);
        Domain::install($uid, $cid, $o['from_bike_id'] ? (int)$o['from_bike_id'] : null, $o['from_parent_id'] ? (int)$o['from_parent_id'] : null,
            $o['from_slot'], $on, 'back from repair', true, $ws, 'STORED');
        return $occ ? 'back on, ' . Domain::componentName(Domain::component($uid, (int)$occ['component_id'])) . ' stored' : 'back on';
    }

    private static function fixIncident(int $uid, array $o, int $cid, string $outcome, string $work, ?int $cost, string $on, int $ws): bool
    {
        $rows = Db::all('SELECT * FROM journal_entries WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [$uid, $o['incident_group']]);
        $mine = array_filter($rows, fn($e) => (int)$e['component_id'] === $cid && !$e['repair']);
        if (!$mine) {
            $mine = array_filter($rows, fn($e) => !$e['component_id'] && !$e['affected'] && !$e['repair']);
        }
        $text = $work . ($o['shop'] ? ' by ' . $o['shop'] : '') . ($cost ? ', ' . money($cost) : '');
        foreach ($mine as $e) {
            Db::run('UPDATE journal_entries SET repair = ?, repair_text = ?, repaired_on = ?, repair_session_id = ? WHERE id = ?',
                [$outcome === 'REPLACED_WARRANTY' ? 'REPLACED' : 'REPAIRED', mb_substr($text, 0, 255), $on, $ws, $e['id']]);
        }
        $open = (int)Db::value('SELECT COUNT(*) FROM journal_entries WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL AND repair IS NULL', [$uid, $o['incident_group']]);
        if ($open === 0) {
            Db::run('UPDATE journal_entries SET resolved_on = COALESCE(resolved_on, ?) WHERE user_id = ? AND incident_group = ? AND voided_at IS NULL', [$on, $uid, $o['incident_group']]);
        }
        return $open === 0;
    }

    public static function rows(int $uid, array $f = []): array
    {
        $sql = 'SELECT o.*, c.label, c.mark, c.component_type, b.name AS bike_name, fb.name AS from_bike, fp.label AS from_parent, r.label AS replacement
            FROM service_orders o JOIN components c ON c.id = o.component_id LEFT JOIN bikes b ON b.id = o.bike_id LEFT JOIN bikes fb ON fb.id = o.from_bike_id
            LEFT JOIN components fp ON fp.id = o.from_parent_id LEFT JOIN components r ON r.id = o.replacement_id WHERE o.user_id = ?';
        $args = [$uid];
        if (!empty($f['out'])) {
            $sql .= " AND o.status = 'OUT'";
        } else {
            $sql .= " AND o.status <> 'VOIDED'";
        }
        if (!empty($f['component_id'])) {
            $sql .= ' AND (o.component_id = ? OR o.replacement_id = ?)';
            $args[] = $f['component_id'];
            $args[] = $f['component_id'];
        }
        if (!empty($f['bike_id'])) {
            $sql .= ' AND o.bike_id = ?';
            $args[] = $f['bike_id'];
        }
        return Db::all($sql . ' ORDER BY o.sent_on DESC, o.id DESC', $args);
    }

    /** Open incidents to link when sending a part away: its own and its bike's. */
    public static function incidentChoices(int $uid, array $c): array
    {
        $out = [];
        $bike = Domain::currentBike($uid, (int)$c['id']);
        foreach (array_merge(Incidents::list($uid, ['component_id' => $c['id'], 'open' => 1]), $bike ? Incidents::list($uid, ['bike_id' => $bike['id'], 'open' => 1]) : []) as $i) {
            $out[$i['group']] = $i['label'] . ' on ' . $i['on'] . ($i['bike_name'] ? ' (' . $i['bike_name'] . ')' : '');
        }
        return $out;
    }
}

final class PartLife
{
    public const SKIP = ['FRAME', 'FORK'];
    public const OUT_OF_USE = ['RETIRED', 'DISCARDED', 'SOLD', 'WARRANTY_RETURN'];

    private static function months(?string $a, ?string $b): ?float
    {
        if (!$a || !$b) {
            return null;
        }
        $d = (int)(new DateTimeImmutable($a))->diff(new DateTimeImmutable($b))->format('%r%a');
        return round(max($d, 0) / 30.44, 1);
    }

    private static function row(int $uid, array $c): array
    {
        $t = Domain::totals($uid, $c);
        $insts = Db::all('SELECT * FROM installations WHERE user_id = ? AND component_id = ? AND voided_at IS NULL ORDER BY installed_on, id', [$uid, $c['id']]);
        $first = $insts[0]['installed_on'] ?? null;
        $bikes = [];
        foreach (Domain::bikePeriods($uid, (int)$c['id']) as $p) {
            $bikes[$p['bike_id']] = true;
        }
        $names = $bikes ? array_column(Db::all('SELECT name FROM bikes WHERE id IN (' . implode(',', array_map('intval', array_keys($bikes))) . ')'), 'name') : [];
        $finished = $c['status'] === 'RETIRED' && in_array($c['disposition'], self::OUT_OF_USE, true);
        $ended = $finished ? $c['retired_on'] : null;
        $lastRemoval = null;
        foreach (array_reverse($insts) as $i) {
            if ($i['removed_on']) {
                $lastRemoval = $i;
                break;
            }
        }
        if ($finished && $lastRemoval) {
            $ended = $lastRemoval['removed_on'];
        }
        $why = null;
        if ($finished) {
            $why = Catalog::raw('dispositions')[$c['disposition']] ?? $c['disposition'];
            $detail = $c['retire_reason'] && mb_strtolower($c['retire_reason']) !== mb_strtolower($why) ? $c['retire_reason'] : ($lastRemoval['removal_reason'] ?? null);
            if ($detail) {
                $why .= " ($detail)";
            }
        }
        $p = $c['product_id'] ? Db::one('SELECT maker, model FROM products WHERE id = ?', [$c['product_id']]) : null;
        $product = $p ? trim($p['maker'] . ' ' . $p['model']) : (trim(($c['maker'] ?? '') . ' ' . ($c['model'] ?? '')) ?: null);
        return ['component' => $c, 'product' => $product, 'bikes' => $names, 'first' => $first, 'ended' => $ended, 'finished' => $finished,
            'months' => $first ? self::months($first, $ended ?? today()) : null, 'km' => $t['total_km'], 'hours' => $t['hours'], 'rides' => $t['rides'],
            'status' => $t['status'], 'why' => $why];
    }

    private static function average(array $rows): array
    {
        $km = array_column($rows, 'km');
        $h = array_filter(array_column($rows, 'hours'));
        $m = array_filter(array_column($rows, 'months'), fn($x) => $x !== null);
        return ['count' => count($rows), 'avg_km' => $km ? array_sum($km) / count($km) : null, 'min_km' => $km ? min($km) : null, 'max_km' => $km ? max($km) : null,
            'avg_hours' => $h ? array_sum($h) / count($h) : null, 'avg_months' => $m ? array_sum($m) / count($m) : null,
            'estimated' => (bool)array_filter($rows, fn($r) => $r['status'] !== 'known')];
    }

    public static function report(int $uid, ?string $type = null): array
    {
        $sql = 'SELECT c.* FROM components c WHERE c.user_id = ? AND c.component_type NOT IN (\'FRAME\',\'FORK\')
            AND EXISTS (SELECT 1 FROM installations i WHERE i.component_id = c.id AND i.voided_at IS NULL)';
        $args = [$uid];
        if ($type) {
            $sql .= ' AND c.component_type = ?';
            $args[] = $type;
        }
        $by = [];
        foreach (Db::all($sql . ' ORDER BY c.label', $args) as $c) {
            $r = self::row($uid, $c);
            $by[$c['component_type']][$r['finished'] ? 'finished' : 'in_use'][] = $r;
        }
        $types = [];
        foreach ($by as $code => $g) {
            $g += ['finished' => [], 'in_use' => []];
            $prods = [];
            foreach ($g['finished'] as $r) {
                $prods[$r['product'] ?? 'No product recorded'][] = $r;
            }
            $products = [];
            foreach ($prods as $name => $rows) {
                $products[] = ['product' => $name] + self::average($rows);
            }
            usort($products, fn($a, $b) => [$b['count'], $a['product']] <=> [$a['count'], $b['product']]);
            usort($g['finished'], fn($a, $b) => strcmp((string)$b['ended'], (string)$a['ended']));
            usort($g['in_use'], fn($a, $b) => $b['km'] <=> $a['km']);
            $types[] = ['code' => $code, 'name' => Catalog::typeName($code), 'finished' => $g['finished'], 'in_use' => $g['in_use'],
                'products' => $products, 'overall' => $g['finished'] ? self::average($g['finished']) : null];
        }
        usort($types, fn($a, $b) => [count($b['finished']), $a['name']] <=> [count($a['finished']), $b['name']]);
        return $types;
    }
}
