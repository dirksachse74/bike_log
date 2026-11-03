<?php
declare(strict_types=1);

// Workshop steps that change several records at once, and overviews built from them. Same rules as the
// desktop app: inventory.replace / group_wheels, spares.replace_options / compatibility,
// maintenance.brake_overview / charge_history.

final class Workshop
{
    public const FIT_TEXT = ['VERIFIED' => 'fits (checked)', 'UNVERIFIED' => 'should fit (not checked)', 'SAME_PRODUCT' => 'same product as now', 'UNKNOWN' => 'fit not known'];
    public const CHARGE_ACTIONS = ['BATTERY_CHARGE', 'POWER_CHARGE'];

    // ------------------------------------------------------------------ product fits a bike

    /** Bikes a product fits: [bike_id, bike, verified, note], checked ones first. */
    public static function fits(int $uid, ?int $productId): array
    {
        if (!$productId) {
            return [];
        }
        return Db::all('SELECT f.id, f.bike_id, b.name AS bike, f.verified, f.note FROM product_bike_fit f JOIN bikes b ON b.id = f.bike_id
            WHERE f.user_id = ? AND f.product_id = ? ORDER BY f.verified DESC, b.name', [$uid, $productId]);
    }

    public static function setFit(int $uid, int $productId, int $bikeId, bool $verified, ?string $note): void
    {
        $p = Db::one('SELECT * FROM products WHERE id = ? AND user_id = ?', [$productId, $uid]) ?? throw new NotFound(t('Product not found.'));
        $b = Domain::bike($uid, $bikeId);
        $note = $note !== null && $note !== '' ? mb_substr($note, 0, 255) : null;
        Db::run('INSERT INTO product_bike_fit (user_id, product_id, bike_id, verified, note, created_at) VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE verified = VALUES(verified), note = VALUES(note)', [$uid, $productId, $bikeId, $verified ? 1 : 0, $note, now_utc()]);
        ChangeLog::note($uid, 'product', $productId, trim($p['maker'] . ' ' . $p['model']) . ' ' . ($verified ? 'fits' : t('should fit')) . ' ' . $b['name']
            . ($note ? " ($note)" : ''), $bikeId);
    }

    public static function removeFit(int $uid, int $productId, int $bikeId): void
    {
        $n = Db::run('DELETE FROM product_bike_fit WHERE user_id = ? AND product_id = ? AND bike_id = ?', [$uid, $productId, $bikeId])->rowCount();
        if ($n) {
            ChangeLog::note($uid, 'product', $productId, t('Fit with {bike} removed', ['bike' => Domain::bike($uid, $bikeId)['name']]), $bikeId);
        }
    }

    /** How sure we are that a product fits a bike: VERIFIED, UNVERIFIED, SAME_PRODUCT (as the part it replaces) or UNKNOWN. */
    public static function fitFor(int $uid, ?int $productId, ?int $bikeId, ?int $currentProductId = null): string
    {
        if ($productId && $bikeId) {
            $f = Db::one('SELECT verified FROM product_bike_fit WHERE user_id = ? AND product_id = ? AND bike_id = ?', [$uid, $productId, $bikeId]);
            if ($f) {
                return (int)$f['verified'] ? 'VERIFIED' : 'UNVERIFIED';
            }
        }
        return $productId && $productId === $currentProductId ? 'SAME_PRODUCT' : 'UNKNOWN';
    }

    // ------------------------------------------------------------------ replace a part

    private static function openChildren(int $uid, int $componentId): array
    {
        return Db::all('SELECT i.id AS installation_id, i.slot, c.* FROM installations i JOIN components c ON c.id = i.component_id
            WHERE i.user_id = ? AND i.parent_component_id = ? AND i.removed_on IS NULL AND i.voided_at IS NULL ORDER BY i.slot, c.label', [$uid, $componentId]);
    }

    /** Everything the Replace form needs, preselected for the part that comes off. */
    public static function replaceOptions(int $uid, int $componentId): array
    {
        $c = Domain::component($uid, $componentId);
        $open = Domain::openInstallation($uid, $componentId) ?? throw new UserError(t('{part} is not installed, so there is nothing to replace.', ['part' => Domain::componentName($c)]));
        $bike = Domain::currentBike($uid, $componentId);
        $bikeId = $bike ? (int)$bike['id'] : null;
        $cur = $c['product_id'] ? (int)$c['product_id'] : null;
        $spares = [];
        foreach (Inventory::individualSpares($uid, $c['component_type']) as $s) {
            if ((int)$s['id'] === $componentId) {
                continue;
            }
            $s['fit'] = self::fitFor($uid, $s['product_id'] ? (int)$s['product_id'] : null, $bikeId, $cur);
            $s['mounted'] = self::openChildren($uid, (int)$s['id']);
            $s['km'] = Domain::totals($uid, $s);
            $spares[] = $s;
        }
        $stock = [];
        foreach (Db::all("SELECT * FROM consumables WHERE user_id = ? AND tracking_mode = 'COUNTED' AND component_type = ? AND archived_at IS NULL ORDER BY name",
            [$uid, $c['component_type']]) as $l) {
            $l['level'] = Inventory::stockLevel($uid, (int)$l['id']);
            if ((int)$l['track_stock'] && $l['level'] < 1) {
                continue;
            }
            $l['fit'] = self::fitFor($uid, $l['product_id'] ? (int)$l['product_id'] : null, $bikeId, $cur);
            $stock[] = $l;
        }
        $children = [];
        foreach (self::openChildren($uid, $componentId) as $ch) {
            // a part whose own rule says "replace it now" (a quick link that has served its chains) stays behind by default
            $due = null;
            foreach (Reminders::rulesFor($uid, $ch) as $rule) {
                if ($rule['trigger_kind'] === 'PARENT_COUNT') {
                    $r = Reminders::evaluateComponent($uid, $rule, $ch, $bike ?? Domain::RIDER);
                    if (in_array($r['status'], ['OVERDUE', 'SOON'], true)) {
                        $due = $r['text'];
                    }
                }
            }
            $ch['carry'] = $due === null;
            $ch['note'] = $due;
            $children[] = $ch;
        }
        $product = $cur ? Db::one('SELECT * FROM products WHERE id = ?', [$cur]) : null;
        return ['component' => $c, 'installation' => $open, 'bike' => $bike, 'product' => $product, 'spares' => $spares, 'stock' => $stock,
            'children' => $children, 'suggested_outcome' => Inventory::defaultOutcome($c['component_type']),
            'next_label' => self::nextLabel($uid, $c)];
    }

    /** "Ultegra chain (3)" after "Ultegra chain (2)"; tires and tubes keep their name and get a mark instead. */
    private static function nextLabel(int $uid, array $c): string
    {
        $base = preg_replace('/ \(\d+\)$/', '', (string)$c['label']);
        return Inventory::uniqueLabel($uid, $c['component_type'], $base);
    }

    /**
     * Replace an installed part in the same position, as one step that can be undone.
     * $source: 'spare:ID' (a stored spare), 'stock:ID' (one unit from counted stock), 'same' (a new one of the same
     * product) or 'new' (a new item: $new = label, price_cents, purchase_date, prior_usage, product_id).
     * $carry: ids of parts on the old part that move to the new one (quick link to the new chain, tire to the new wheel).
     */
    public static function replace(int $uid, int $oldId, string $on, string $source, array $new = [], ?string $outcome = null,
                                   array $carry = [], ?string $reason = null): array
    {
        return Db::tx(function () use ($uid, $oldId, $on, $source, $new, $outcome, $carry, $reason) {
            $old = Domain::component($uid, $oldId);
            $inst = Domain::openInstallation($uid, $oldId) ?? throw new UserError(t('{part} is not installed, so there is nothing to replace.', ['part' => Domain::componentName($old)]));
            $outcome = $outcome !== null && $outcome !== '' ? $outcome : Inventory::defaultOutcome($old['component_type']);
            if (!isset(Inventory::dispositions()[$outcome])) {
                throw new UserError(t('Choose what happened to the old part.'));
            }
            if ($on <= $inst['installed_on']) {
                throw new UserError(t('{part} was fitted on {date}; the change must be later.', ['part' => Domain::componentName($old), 'date' => $inst['installed_on']]));
            }
            $children = [];
            foreach (self::openChildren($uid, $oldId) as $ch) {
                $children[(int)$ch['id']] = $ch;
            }
            $carry = array_values(array_unique(array_map('intval', $carry)));
            foreach ($carry as $cid) {
                if (!isset($children[$cid])) {
                    throw new UserError(t('Only parts mounted on the old part can move to the new one.'));
                }
            }
            $left = [];
            $ws = Inventory::startSession($uid, 'REPLACE', t('Replaced {part}', ['part' => Domain::componentName($old)]), $on);
            $label = trim((string)($new['label'] ?? ''));
            if (str_starts_with($source, 'spare:')) {
                $newComp = Domain::component($uid, (int)substr($source, 6));
                if ((int)$newComp['id'] === $oldId) {
                    throw new UserError(t('Pick a different part. To service the same part, use Log maintenance on it.'));
                }
                if ($newComp['component_type'] !== $old['component_type']) {
                    throw new UserError(t('{part} is a {type}, not a {wanted}.', ['part' => Domain::componentName($newComp),
                        'type' => Catalog::typeName($newComp['component_type']), 'wanted' => Catalog::typeName($old['component_type'])]));
                }
                if (Domain::openInstallation($uid, (int)$newComp['id'])) {
                    throw new UserError(t('{part} is fitted somewhere else. Use Move on it instead.', ['part' => Domain::componentName($newComp)]));
                }
                if ($newComp['disposition'] === 'AWAITING_SERVICE') {
                    throw new UserError(t('{part} is waiting for repair. Log the repair first.', ['part' => Domain::componentName($newComp)]));
                }
                // a position the spare already fills (a spare wheelset with its own wheels): that part stays on the old one
                $taken = array_column(self::openChildren($uid, (int)$newComp['id']), null, 'slot');
                foreach ($carry as $k => $cid) {
                    if (isset($taken[$children[$cid]['slot']])) {
                        $left[] = Domain::componentName($children[$cid]);
                        unset($carry[$k]);
                    }
                }
                $carry = array_values($carry);
                $newId = (int)$newComp['id'];
            } elseif (str_starts_with($source, 'stock:')) {
                $line = Db::one('SELECT * FROM consumables WHERE id = ? AND user_id = ?', [(int)substr($source, 6), $uid]) ?? throw new NotFound(t('Stock line not found.'));
                if ($line['component_type'] !== $old['component_type']) {
                    throw new UserError(t('{name} is not stock of {types}.', ['name' => $line['name'], 'types' => lc(Catalog::typePlural($old['component_type']))]));
                }
                $newId = Inventory::drawFromStock($uid, (int)$line['id'], $on, $ws, $label !== '' ? $label : null);
            } elseif ($source === 'same' || $source === 'new') {
                $pid = $source === 'same' ? ($old['product_id'] ? (int)$old['product_id'] : null) : (!empty($new['product_id']) ? (int)$new['product_id'] : null);
                $p = null;
                if ($pid) {
                    $p = Db::one('SELECT * FROM products WHERE id = ? AND user_id = ?', [$pid, $uid]) ?? throw new NotFound(t('Product not found.'));
                    if ($p['component_type'] !== $old['component_type']) {
                        throw new UserError(t('That product is a {type}.', ['type' => Catalog::typeName($p['component_type'])]));
                    }
                }
                $src = $source === 'same' ? $old : ($p ?? []);
                $prior = in_array($new['prior_usage'] ?? 'NEW', ['NEW', 'UNKNOWN'], true) ? ($new['prior_usage'] ?? 'NEW') : 'NEW';
                $newId = Inventory::createComponent($uid, [
                    'component_type' => $old['component_type'], 'product_id' => $pid,
                    'label' => $label !== '' ? $label : self::nextLabel($uid, $old),
                    'maker' => $src['maker'] ?? null, 'model' => $src['model'] ?? null, 'prior_usage' => $prior,
                    'price_cents' => $new['price_cents'] ?? null, 'shop' => $new['shop'] ?? null,
                    'purchase_date' => $new['purchase_date'] ?? $on, 'tire_setup' => $old['tire_setup'], 'work_session_id' => $ws,
                ]);
            } else {
                throw new UserError(t('Choose what goes on instead: a spare, one from stock, the same product or a new item.'));
            }
            // the carried parts come off the old part first, then the new part takes the position
            foreach ($carry as $cid) {
                Db::run("UPDATE installations SET removed_on = ?, removal_reason = 'Moved', removal_outcome = 'MOVED', removal_session_id = ? WHERE id = ?",
                    [$on, $ws, $children[$cid]['installation_id']]);
            }
            $newInst = Domain::install($uid, $newId, $inst['bike_id'] ? (int)$inst['bike_id'] : null,
                $inst['parent_component_id'] ? (int)$inst['parent_component_id'] : null, $inst['slot'], $on, null, true, $ws, $outcome);
            if ($reason !== null && $reason !== '') {
                Db::run('UPDATE installations SET removal_reason = ? WHERE id = ?', [mb_substr($reason, 0, 255), $inst['id']]);
            }
            foreach ($carry as $cid) {
                Domain::install($uid, $cid, null, $newId, $children[$cid]['slot'], $on, null, false, $ws);
            }
            Inventory::ensureWheels($uid, $newId, $on, $ws);
            if ($old['component_type'] === 'CHAIN' && $old['rotation_bike_id'] && $inst['bike_id']) {
                $nc = Domain::component($uid, $newId);
                if ($nc['rotation_bike_id'] === null) {
                    Db::updateOwned('components', $newId, $uid, ['rotation_bike_id' => (int)$inst['bike_id']]);
                }
            }
            $newC = Domain::component($uid, $newId);
            ChangeLog::note($uid, 'part', $oldId, t('Replaced by {part} on {date} ({what})', ['part' => Domain::componentName($newC), 'date' => $on, 'what' => Inventory::dispositions()[$outcome] ?? $outcome])
                . ($carry ? t(', {n} mounted part(s) moved over', ['n' => count($carry)]) : ''),
                $inst['bike_id'] ? (int)$inst['bike_id'] : null, $oldId);
            return ['work_session_id' => $ws, 'new_component_id' => $newId, 'installation_id' => $newInst, 'outcome' => $outcome, 'label' => Domain::componentName($newC),
                'carried' => count($carry), 'left_on_old' => $left];
        });
    }

    // ------------------------------------------------------------------ wheels into a wheelset

    /** Wheels fitted directly on a bike (no wheelset). */
    public static function looseWheels(int $uid, int $bikeId): array
    {
        return Db::all("SELECT i.id AS installation_id, i.slot, i.installed_on, c.* FROM installations i JOIN components c ON c.id = i.component_id
            WHERE i.user_id = ? AND i.bike_id = ? AND i.slot IN ('FRONT_WHEEL', 'REAR_WHEEL') AND i.removed_on IS NULL AND i.voided_at IS NULL ORDER BY i.slot", [$uid, $bikeId]);
    }

    /** Spare wheelsets that have room for the loose wheels. */
    public static function wheelsetChoices(int $uid, int $bikeId): array
    {
        $slots = array_column(self::looseWheels($uid, $bikeId), 'slot');
        $out = [];
        foreach (Inventory::individualSpares($uid, 'WHEELSET') as $w) {
            if (!array_intersect($slots, array_column(self::openChildren($uid, (int)$w['id']), 'slot'))) {
                $out[] = $w;
            }
        }
        return $out;
    }

    /**
     * Put the wheels fitted directly on a bike into a wheelset (a new one, or a spare one) from a date, as one step.
     * From then on the wheelset counts km too; the wheels and everything on them carry on with their own km.
     */
    public static function groupWheels(int $uid, int $bikeId, string $on, ?string $label = null, ?int $wheelsetId = null): array
    {
        return Db::tx(function () use ($uid, $bikeId, $on, $label, $wheelsetId) {
            $bike = Domain::bike($uid, $bikeId);
            $wheels = self::looseWheels($uid, $bikeId);
            if (!$wheels) {
                throw new UserError(t('{bike} has no wheels fitted directly.', ['bike' => $bike['name']]));
            }
            foreach ($wheels as $w) {
                if ($on <= $w['installed_on']) {
                    throw new UserError(t('{part} was fitted on {date}; pick a later date.', ['part' => Domain::componentName($w), 'date' => $w['installed_on']]));
                }
            }
            if (Db::one("SELECT id FROM installations WHERE user_id = ? AND bike_id = ? AND slot = 'WHEELSET' AND removed_on IS NULL AND voided_at IS NULL", [$uid, $bikeId])) {
                throw new UserError(t('{bike} already has a wheelset.', ['bike' => $bike['name']]));
            }
            $ws = Inventory::startSession($uid, 'GROUP_WHEELS', t('Wheels of {bike} put into a wheelset', ['bike' => $bike['name']]), $on);
            if ($wheelsetId) {
                $set = Domain::component($uid, $wheelsetId);
                if ($set['component_type'] !== 'WHEELSET') {
                    throw new UserError(t('{part} is not a wheelset.', ['part' => Domain::componentName($set)]));
                }
                if (!in_array((int)$set['id'], array_map('intval', array_column(self::wheelsetChoices($uid, $bikeId), 'id')), true)) {
                    throw new UserError(t('{part} is fitted somewhere or already has wheels in those positions.', ['part' => Domain::componentName($set)]));
                }
            } else {
                $name = trim((string)$label) !== '' ? trim((string)$label) : t('Wheelset ({bike})', ['bike' => $bike['name']]);
                $tire = $wheels[0]['tire_setup'];
                $wheelsetId = Inventory::createComponent($uid, ['component_type' => 'WHEELSET', 'label' => Inventory::uniqueLabel($uid, 'WHEELSET', $name),
                    'prior_usage' => 'NEW', 'purchase_date' => $on, 'tire_setup' => $tire, 'work_session_id' => $ws,
                    'notes' => t('Made from the wheels of {bike}', ['bike' => $bike['name']])]);
            }
            foreach ($wheels as $w) {
                Db::run("UPDATE installations SET removed_on = ?, removal_reason = 'Put into a wheelset', removal_outcome = 'MOVED', removal_session_id = ? WHERE id = ?",
                    [$on, $ws, $w['installation_id']]);
            }
            Domain::install($uid, $wheelsetId, $bikeId, null, 'WHEELSET', $on, null, false, $ws);
            foreach ($wheels as $w) {
                Domain::install($uid, (int)$w['id'], null, $wheelsetId, $w['slot'], $on, null, false, $ws);
            }
            $set = Domain::component($uid, $wheelsetId);
            ChangeLog::note($uid, 'part', $wheelsetId, t('{n} wheel(s) of {bike} put into {set} on {date}', ['n' => count($wheels), 'bike' => $bike['name'], 'set' => Domain::componentName($set), 'date' => $on]), $bikeId, $wheelsetId);
            return ['wheelset_id' => $wheelsetId, 'work_session_id' => $ws, 'wheels' => array_map('intval', array_column($wheels, 'id'))];
        });
    }

    // ------------------------------------------------------------------ brakes

    /** Every brake circuit in use: where it is, the brake fluid reminder and the last bleed (symptom, work done, result). */
    public static function brakeOverview(int $uid, ?int $bikeId = null): array
    {
        $out = [];
        foreach (Db::all("SELECT * FROM components WHERE user_id = ? AND component_type = 'BRAKE_CIRCUIT' AND status = 'ACTIVE' ORDER BY label", [$uid]) as $c) {
            $bike = Domain::currentBike($uid, (int)$c['id']);
            if ($bikeId !== null && (!$bike || (int)$bike['id'] !== $bikeId)) {
                continue;
            }
            $open = Domain::openInstallation($uid, (int)$c['id']);
            $fluid = null;
            foreach (Reminders::rulesFor($uid, $c) as $rule) {
                if ($rule['action_code'] === 'BRAKE_FLUID_REPLACE') {
                    $fluid = $bike ? Reminders::evaluateComponent($uid, $rule, $c, $bike)
                        : ['status' => 'UNKNOWN', 'text' => t('Not on a bike, so no km count.')];
                }
            }
            $last = fn(array $codes) => Db::one('SELECT * FROM maintenance_events WHERE user_id = ? AND component_id = ? AND voided_at IS NULL AND action_code IN ('
                . implode(',', array_fill(0, count($codes), '?')) . ') ORDER BY performed_on DESC, id DESC LIMIT 1', array_merge([$uid, $c['id']], $codes));
            $out[] = ['component' => $c, 'bike' => $bike, 'position' => $open ? Catalog::slotName($open['slot']) : null,
                'fluid' => $fluid, 'last_bleed' => $last(['BRAKE_BLEED']), 'last_fluid' => $last(['BRAKE_FLUID_REPLACE']), 'last_check' => $last(['BRAKE_CHECK'])];
        }
        return $out;
    }

    // ------------------------------------------------------------------ charging

    /**
     * Every charge of a part that is charged (power-meter pedals, Di2 battery, computer ...), newest first, with the
     * riding between one charge and the next: km, ride hours, rides and days. Null for parts that are not charged.
     */
    public static function chargeHistory(int $uid, array $c): ?array
    {
        $actions = array_values(array_intersect(self::CHARGE_ACTIONS, array_keys(Catalog::actionsFor($c['component_type']))));
        if (!$actions) {
            return null;
        }
        $in = implode(',', array_fill(0, count($actions), '?'));
        $events = Db::all("SELECT id, performed_on, action_code FROM maintenance_events WHERE user_id = ? AND component_id = ? AND voided_at IS NULL
            AND action_code IN ($in) ORDER BY performed_on, id", array_merge([$uid, $c['id']], $actions));
        $rows = [];
        $today = today();
        foreach ($events as $n => $e) {
            $next = $events[$n + 1] ?? null;
            $until = $next['performed_on'] ?? null;
            // two charges on one day: the rides of that day go to the later one
            $u = $until !== null && $until === $e['performed_on'] ? ['km' => 0.0, 'seconds' => 0, 'rides' => 0, 'missing_duration' => 0]
                : Domain::rideUsage($uid, $c, $e['performed_on'], $until);
            $rows[] = ['event_id' => (int)$e['id'], 'charged_on' => $e['performed_on'], 'until' => $until,
                'days' => (int)(new DateTimeImmutable($e['performed_on']))->diff(new DateTimeImmutable($until ?? $today))->days,
                'km' => round($u['km'], 1), 'hours' => round($u['seconds'] / 3600, 1), 'rides' => $u['rides'], 'rides_without_time' => $u['missing_duration']];
        }
        $done = array_values(array_filter($rows, fn($r) => $r['until'] !== null));
        $avg = null;
        if ($done) {
            $n = count($done);
            $avg = ['km' => round(array_sum(array_column($done, 'km')) / $n, 1), 'hours' => round(array_sum(array_column($done, 'hours')) / $n, 1),
                'days' => (int)round(array_sum(array_column($done, 'days')) / $n), 'charges' => $n];
        }
        return ['actions' => $actions, 'charges' => array_reverse($rows), 'since_last' => $rows ? $rows[count($rows) - 1] : null, 'average' => $avg];
    }
}
