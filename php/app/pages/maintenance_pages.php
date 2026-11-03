<?php
declare(strict_types=1);

// Maintenance log, reminders, service intervals, supplies (consumables).

function page_maintenance(): void
{
    $uid = (int)require_user()['id'];
    $events = Db::all('SELECT e.*, c.label, c.mark, c.component_type, b.name AS bike_name, s.name AS consumable_name FROM maintenance_events e
        LEFT JOIN components c ON c.id = e.component_id LEFT JOIN bikes b ON b.id = e.bike_id LEFT JOIN consumables s ON s.id = e.consumable_id
        WHERE e.user_id = ? ORDER BY e.performed_on DESC, e.id DESC LIMIT 200', [$uid]);
    View::render('maintenance/list', compact('events'), t('Maintenance'), 'maintenance');
}

function page_log(): void
{
    $uid = (int)require_user()['id'];
    $componentId = get_int('part');
    $bikeId = get_int('bike');
    if (Request::isPost()) {
        $target = post('target');   // "c:12" or "b:3"
        $cid = str_starts_with($target, 'c:') ? (int)substr($target, 2) : 0;
        $bid = str_starts_with($target, 'b:') ? (int)substr($target, 2) : 0;
        $actionCode = post('action_code');
        $action = Catalog::action($actionCode);
        $mv = parse_number(post('measurement_value'), t('Measurement'));
        Domain::logMaintenance($uid, [
            'action_code' => $actionCode, 'component_id' => $cid ?: null, 'bike_id' => $bid ?: null,
            'performed_on' => parse_date(post('performed_on'), true),
            'outcome' => $action && $action['outcomes'] && in_array(post('outcome'), $action['outcomes'], true) ? post('outcome') : null,
            'measurement_value' => $mv, 'consumable_id' => (int)post('consumable_id') ?: null,
            'consumable_qty' => parse_number(post('consumable_qty'), t('Amount used')), 'cost_cents' => parse_money_cents(post('cost'), t('Cost')),
            'shop' => nullable(post('shop')), 'notes' => nullable(post('notes')),
            'symptom' => $action && in_array('symptom', $action['fields'], true) ? nullable(post('symptom')) : null,
            'work_done' => $action && in_array('work_done', $action['fields'], true) ? nullable(post('work_done')) : null,
        ]);
        Session::flash('ok', t('{what} logged. Reminders that this resets start counting again.', ['what' => $action ? Catalog::actionName($action['code']) : t('Work')]));
        redirect($cid ? 'part' : 'bike', ['id' => $cid ?: $bid]);
    }
    // targets: all active parts on bikes and the bikes themselves
    $targets = [];
    foreach (Db::all("SELECT * FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]) as $b) {
        $group = $b['name'];
        $targets[$group]['b:' . $b['id']] = t('Whole bike');
        foreach (Domain::installedOn($uid, (int)$b['id']) as $p) {
            $targets[$group]['c:' . $p['id']] = str_repeat('  ', (int)$p['depth']) . Catalog::typeName($p['component_type']) . ': ' . Domain::componentName($p);
        }
    }
    $spares = Db::all("SELECT * FROM components WHERE user_id = ? AND status = 'ACTIVE' ORDER BY component_type, label", [$uid]);
    foreach ($spares as $s) {
        $key = 'c:' . $s['id'];
        $found = false;
        foreach ($targets as $g) {
            $found = $found || isset($g[$key]);
        }
        if (!$found) {
            $targets[t('Not on a bike')][$key] = Catalog::typeName($s['component_type']) . ': ' . Domain::componentName($s);
        }
    }
    $selected = $componentId ? 'c:' . $componentId : ($bikeId ? 'b:' . $bikeId : '');
    $types = [];
    foreach (Db::all('SELECT id, component_type FROM components WHERE user_id = ?', [$uid]) as $r) {
        $types['c:' . $r['id']] = $r['component_type'];
    }
    $actionsByType = [];
    foreach (array_merge(['BIKE'], array_unique(array_values($types))) as $t) {
        $actionsByType[$t] = array_map(fn($a) => ['name' => t($a['name']), 'outcomes' => $a['outcomes'], 'labels' => array_combine($a['outcomes'], array_map([Catalog::class, 'label'], $a['outcomes'])) ?: new stdClass(), 'unit' => $a['unit'],
            'measure' => in_array('measurement', $a['fields'], true), 'consumable' => in_array('consumable', $a['fields'], true),
            'symptom' => in_array('symptom', $a['fields'], true), 'work_done' => in_array('work_done', $a['fields'], true)],
            Catalog::actionsFor($t));
    }
    $consumables = Db::all('SELECT id, name, unit FROM consumables WHERE user_id = ? AND archived_at IS NULL ORDER BY name', [$uid]);
    View::render('maintenance/log', ['targets' => $targets, 'selected' => $selected, 'types' => $types, 'actionsByType' => $actionsByType,
        'consumables' => $consumables, 'preAction' => get_param('action')], t('Log maintenance'), 'maintenance');
}

function page_event_void(): void
{
    $uid = (int)require_user()['id'];
    $e = Db::one('SELECT * FROM maintenance_events WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound(t('Entry not found.'));
    if (Request::isPost()) {
        Domain::voidMaintenance($uid, (int)$e['id'], post('reason'));
        Session::flash('ok', t('Entry marked as wrong. It stays visible (crossed out) and no longer resets reminders.'));
    }
    redirect($e['component_id'] ? 'part' : 'bike', ['id' => $e['component_id'] ?: $e['bike_id']]);
}

function page_reminders(): void
{
    $uid = (int)require_user()['id'];
    $all = Reminders::forUser($uid);
    View::render('maintenance/reminders', ['reminders' => $all], t('What needs attention'), 'home');
}

function page_snooze(): void
{
    $uid = (int)require_user()['id'];
    if (!Request::isPost()) {
        redirect('reminders');
    }
    $cid = (int)post('component_id');
    $bid = (int)post('bike_id');
    $code = post('rule_code');
    if ($cid) {
        Domain::component($uid, $cid);
    } else {
        Domain::bike($uid, $bid);
    }
    if (post('do') === 'clear') {
        Db::run('UPDATE reminder_snoozes SET cleared_at = ? WHERE user_id = ? AND rule_code = ? AND ' . ($cid ? 'component_id = ?' : 'bike_id = ?') . ' AND cleared_at IS NULL',
            [now_utc(), $uid, $code, $cid ?: $bid]);
        Session::flash('ok', t('Snooze ended.'));
    } else {
        $days = (int)post('days');
        $moreKm = parse_number(post('km'), t('Km'));
        if ($days <= 0 && !$moreKm) {
            throw new UserError(t('Snooze for some days or some km.'));
        }
        $usedNow = (float)post('used_km');
        Db::insert('reminder_snoozes', ['user_id' => $uid, 'component_id' => $cid ?: null, 'bike_id' => $cid ? null : $bid, 'rule_code' => $code,
            'until_date' => $days > 0 ? (new DateTimeImmutable(today()))->modify("+$days days")->format('Y-m-d') : null,
            'until_km' => $moreKm ? $usedNow + $moreKm : null, 'note' => nullable(post('note')), 'created_at' => now_utc()]);
        Session::flash('ok', t('Reminder snoozed. No maintenance was recorded.'));
    }
    $back = post('back');
    redirect(in_array($back, ['home', 'reminders', 'part', 'bike'], true) ? $back : 'reminders', $back === 'part' ? ['id' => $cid] : ($back === 'bike' ? ['id' => (int)post('back_id')] : []));
}

function page_rules(): void
{
    $uid = (int)require_user()['id'];
    $rules = Db::all('SELECT r.*, c.label FROM service_rules r LEFT JOIN components c ON c.id = r.component_id WHERE r.user_id = ?
        ORDER BY r.component_id IS NOT NULL, r.component_type, r.name', [$uid]);
    View::render('maintenance/rules', compact('rules'), t('Service intervals'), 'maintenance');
}

function page_rule_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $forPart = get_int('part');
    if ($id) {
        $rule = Db::one('SELECT * FROM service_rules WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound(t('Rule not found.'));
    } elseif ($forPart) {
        // a part-level copy of a type rule: changes the interval for this one part only
        $c = Domain::component($uid, $forPart);
        $src = Db::one('SELECT * FROM service_rules WHERE user_id = ? AND component_type = ? AND rule_code = ?', [$uid, $c['component_type'], get_param('code')])
            ?? throw new NotFound(t('Rule not found.'));
        $rule = $src;
        $rule['id'] = 0;
        $rule['component_type'] = null;
        $rule['component_id'] = $forPart;
        $rule['origin'] = 'PERSONAL';
    } else {
        throw new NotFound(t('Rule not found.'));
    }
    if (Request::isPost()) {
        $row = [
            'name' => post('name') ?: $rule['name'],
            'interval_km' => parse_number(post('interval_km'), t('Km interval')), 'warn_km' => parse_number(post('warn_km'), t('Warn km')),
            'interval_months' => post('interval_months') === '' ? null : (int)post('interval_months'), 'warn_days' => post('warn_days') === '' ? null : (int)post('warn_days'),
            'interval_hours' => parse_number(post('interval_hours'), t('Hours')), 'warn_hours' => parse_number(post('warn_hours'), t('Warn hours')),
            'origin' => in_array(post('origin'), ['DEFAULT', 'MANUFACTURER', 'PERSONAL'], true) ? post('origin') : 'PERSONAL',
            'active' => post('active') === '1' ? 1 : 0, 'notes' => nullable(post('notes')), 'updated_at' => now_utc(),
        ];
        if ($rule['trigger_kind'] === 'CYCLE_WINDOW') {
            $row['window_min_km'] = parse_number(post('window_min_km'), t('Window from'));
            $row['window_max_km'] = parse_number(post('window_max_km'), t('Window to'));
            if ($row['window_min_km'] === null || $row['window_max_km'] === null || $row['window_min_km'] > $row['window_max_km']) {
                throw new UserError(t('Give the window as "from" and "to" km (from ≤ to).'));
            }
            $row['interval_km'] = null;
        } elseif ($rule['trigger_kind'] === 'PARENT_COUNT') {
            $n = post('interval_count');
            if (!ctype_digit($n) || (int)$n < 1 || (int)$n > 50) {
                throw new UserError(t('Give a number from 1 to 50.'));
            }
            $row['interval_count'] = (int)$n;
        } elseif ($rule['action_code'] === 'WAX_HOT') {
            $row['after_top_up_km'] = parse_number(post('after_top_up_km'), t('Km after a top-up'));
        }
        if (in_array($rule['trigger_kind'], ['INTERVAL'], true) && $row['interval_km'] === null && $row['interval_months'] === null && $row['interval_hours'] === null) {
            throw new UserError(t('Give at least one interval (km, months or hours), or switch the rule off.'));
        }
        if ($rule['id']) {
            Db::updateOwned('service_rules', (int)$rule['id'], $uid, $row);
        } else {
            Db::insert('service_rules', $row + ['user_id' => $uid, 'rule_code' => $rule['rule_code'], 'component_id' => $rule['component_id'],
                'action_code' => $rule['action_code'], 'reset_actions' => $rule['reset_actions'], 'trigger_kind' => $rule['trigger_kind'],
                'cycle_action_code' => $rule['cycle_action_code'],
                'window_min_km' => $row['window_min_km'] ?? $rule['window_min_km'], 'window_max_km' => $row['window_max_km'] ?? $rule['window_max_km'],
                'after_top_up_km' => array_key_exists('after_top_up_km', $row) ? $row['after_top_up_km'] : $rule['after_top_up_km'],
                'interval_count' => $row['interval_count'] ?? $rule['interval_count'],
                'requires_setup' => $rule['requires_setup'], 'created_at' => now_utc()]);
        }
        Session::flash('ok', t('Interval saved.'));
        if ($rule['component_id']) {
            redirect('part', ['id' => $rule['component_id']]);
        }
        redirect('rules');
    }
    View::render('maintenance/rule_edit', compact('rule'), t('Change interval'), 'maintenance');
}

function page_rule_delete(): void
{
    $uid = (int)require_user()['id'];
    $rule = Db::one('SELECT * FROM service_rules WHERE id = ? AND user_id = ? AND component_id IS NOT NULL', [get_int('id'), $uid])
        ?? throw new NotFound(t('Only part-level intervals can be removed.'));
    if (Request::isPost()) {
        Db::run('DELETE FROM service_rules WHERE id = ? AND user_id = ?', [$rule['id'], $uid]);
        Session::flash('ok', t('This part uses the normal interval again.'));
    }
    redirect('part', ['id' => $rule['component_id']]);
}

// ------------------------------------------------------------------ supplies

function page_supplies(): void
{
    $uid = (int)require_user()['id'];
    $items = Db::all('SELECT * FROM consumables WHERE user_id = ? ORDER BY archived_at IS NOT NULL, kind, name', [$uid]);
    foreach ($items as &$i) {
        $i['stock'] = Domain::stock($uid, (int)$i['id']);
        $i['last_used'] = Db::value("SELECT MAX(happened_on) FROM consumable_txns WHERE consumable_id = ? AND kind = 'USE' AND voided_at IS NULL", [$i['id']]);
    }
    unset($i);
    View::render('consumables/list', compact('items'), t('Supplies'), 'supplies');
}

function page_supply_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $item = $id ? (Db::one('SELECT * FROM consumables WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound(t('Not found.')))
        : ['id' => 0, 'kind' => get_param('mode') === 'COUNTED' ? 'OTHER' : 'WAX', 'name' => '', 'maker' => '', 'unit' => 'ml', 'track_stock' => 1, 'notes' => '',
            'archived_at' => null, 'tracking_mode' => get_param('mode') === 'COUNTED' ? 'COUNTED' : 'BULK', 'component_type' => null, 'min_stock' => null, 'storage_location' => ''];
    if (Request::isPost()) {
        if (post('do') === 'archive' || post('do') === 'unarchive') {
            Db::updateOwned('consumables', $id, $uid, ['archived_at' => post('do') === 'archive' ? now_utc() : null]);
            redirect('supplies');
        }
        if (post('name') === '') {
            throw new UserError(t('Please enter a name.'));
        }
        if (Db::one('SELECT id FROM consumables WHERE user_id = ? AND name = ? AND id <> ?', [$uid, post('name'), $id])) {
            throw new UserError(t('You already have a supply with that name.'));
        }
        $row = ['kind' => isset(Catalog::CONSUMABLE_KINDS[post('kind')]) ? post('kind') : 'OTHER', 'name' => post('name'),
            'maker' => nullable(post('maker')), 'unit' => post('unit') ?: 'ml', 'track_stock' => post('track_stock') === '1' ? 1 : 0, 'notes' => nullable(post('notes')),
            'min_stock' => parse_number(post('min_stock'), t('Keep at least')), 'storage_location' => nullable(mb_substr(post('storage_location'), 0, 160))];
        $units = Catalog::raw('stock_units');
        if (post('tracking_mode') === 'COUNTED') {
            if (!isset($units[post('component_type')])) {
                throw new UserError(t('Counted stock: choose what kind of part it is.'));
            }
            $row['tracking_mode'] = 'COUNTED';
            $row['component_type'] = post('component_type');
            $row['unit'] = $units[post('component_type')][0];
            $row['kind'] = 'OTHER';
        } else {
            $row['tracking_mode'] = 'BULK';
            $row['component_type'] = null;
        }
        if ($id) {
            Db::updateOwned('consumables', $id, $uid, $row);
        } else {
            $id = Db::insert('consumables', $row + ['user_id' => $uid, 'created_at' => now_utc()]);
            $qty = parse_number(post('initial_qty'), t('Amount'));
            if ($qty) {
                Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $id, 'kind' => 'BUY', 'qty' => $qty, 'happened_on' => today(),
                    'cost_cents' => parse_money_cents(post('initial_cost'), t('Cost')), 'note' => t('Stock when added'), 'created_at' => now_utc()]);
            }
        }
        Session::flash('ok', t('Saved.'));
        redirect('supply', ['id' => $id]);
    }
    View::render('consumables/edit', compact('item'), $id ? t('Edit {name}', ['name' => $item['name']]) : t('Add a supply'), 'supplies');
}

function page_supply(): void
{
    $uid = (int)require_user()['id'];
    $item = Db::one('SELECT * FROM consumables WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound(t('Not found.'));
    if (Request::isPost()) {
        if (post('do') === 'void') {
            Db::run('UPDATE consumable_txns SET voided_at = ? WHERE id = ? AND user_id = ? AND maintenance_event_id IS NULL', [now_utc(), (int)post('txn'), $uid]);
            Session::flash('ok', t('Entry voided.'));
        } else {
            $kind = in_array(post('kind'), ['BUY', 'USE', 'ADJUST'], true) ? post('kind') : 'BUY';
            $qty = parse_number(post('qty'), t('Amount'), $kind === 'ADJUST');
            if (!$qty) {
                throw new UserError(t('Enter an amount.'));
            }
            Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $item['id'], 'kind' => $kind, 'qty' => $qty,
                'happened_on' => parse_date(post('happened_on'), true), 'cost_cents' => parse_money_cents(post('cost'), t('Cost')),
                'note' => nullable(post('note')), 'created_at' => now_utc()]);
            Session::flash('ok', t('Saved.'));
        }
        redirect('supply', ['id' => $item['id']]);
    }
    $txns = Db::all('SELECT * FROM consumable_txns WHERE user_id = ? AND consumable_id = ? ORDER BY happened_on DESC, id DESC', [$uid, $item['id']]);
    $stock = Domain::stock($uid, (int)$item['id']);
    View::render('consumables/show', compact('item', 'txns', 'stock'), $item['name'], 'supplies');
}
