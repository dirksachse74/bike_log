<?php
declare(strict_types=1);

// Groupset import, work steps (undo), spares and stock, shopping list, my settings.

function page_groupset(): void
{
    $uid = (int)require_user()['id'];
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    $templates = Groupsets::templates();
    $code = Request::isPost() ? post('tpl') : get_param('tpl');
    if ($code === '' || !isset($templates[$code])) {
        View::render('groupsets/choose', ['templates' => $templates, 'bikes' => $bikes, 'bikeId' => get_int('bike')], 'Add a groupset', 'parts');
        return;
    }
    $t = $templates[$code];
    $bikeId = Request::isPost() ? (int)post('bike_id') : get_int('bike');
    $opts = [];
    foreach ($t['options'] as $o) {
        $v = $_POST['opt'][$o['key']] ?? null;
        $opts[$o['key']] = is_string($v) ? $v : $o['default'];
    }
    $form = [
        'on' => Request::isPost() ? post('on', today()) : today(),
        'prefix' => Request::isPost() ? post('prefix') : ($t['label_prefix'] ?? $t['series']),
        'occupied' => post('occupied', 'KEEP') === 'REPLACE' ? 'REPLACE' : 'KEEP',
        'prior' => post('prior', 'NEW') === 'UNKNOWN' ? 'UNKNOWN' : 'NEW',
        'purchase_date' => post('purchase_date'),
        'bundle_price' => post('bundle_price'),
        'merchant' => post('merchant'),
    ];
    $include = Request::isPost() && post('picked') === '1' ? post_list('include') : null;
    $spares = post_list('spare');
    $prices = [];
    foreach ((array)($_POST['price'] ?? []) as $k => $v) {
        if (is_string($k) && is_string($v) && trim($v) !== '') {
            $prices[$k] = parse_money_cents($v, 'Price');
        }
    }
    if (Request::isPost() && post('do') === 'import') {
        $bundlePrice = parse_money_cents($form['bundle_price'], 'Total price');
        if ($bundlePrice !== null && $prices) {
            throw new UserError('Give either a total price or prices per part, not both.');
        }
        $res = Db::tx(function () use ($uid, $code, $form, $bikeId, $opts, $include, $prices, $spares, $bundlePrice, $t) {
            $res = Groupsets::import($uid, $code, parse_date($form['on'], true), $bikeId ?: null, $opts, $include, $form['prefix'],
                $form['occupied'], $form['prior'], parse_date($form['purchase_date']), $prices, $spares);
            if ($bundlePrice !== null) {
                Bundles::create($uid, $t['name'], array_values($res['created']), nullable($form['merchant']),
                    parse_date($form['purchase_date']) ?? parse_date($form['on'], true), $bundlePrice, null, $res['work_session_id']);
            }
            return $res;
        });
        $c = $res['plan']['counts'];
        Session::flash('ok', 'Groupset added: ' . $c['INSTALL'] . ' installed, ' . $c['REPLACE'] . ' replaced, ' . $c['SPARE'] . ' as spares. You can undo it here.');
        redirect('ws', ['id' => $res['work_session_id']]);
    }
    $plan = null;
    $error = null;
    try {
        $plan = Groupsets::plan($uid, $code, $bikeId ?: null, $opts, $include, $form['prefix'], $form['occupied'], $spares);
    } catch (UserError $e) {
        $error = $e->getMessage();
    }
    View::render('groupsets/plan', compact('t', 'code', 'bikes', 'bikeId', 'opts', 'form', 'plan', 'error', 'include', 'spares', 'prices'),
        'Add a groupset', 'parts');
}

function page_ws(): void
{
    $uid = (int)require_user()['id'];
    $ws = Db::one('SELECT * FROM work_sessions WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound('Not found.');
    $created = Db::all('SELECT * FROM components WHERE user_id = ? AND work_session_id = ? ORDER BY id', [$uid, $ws['id']]);
    $installs = Db::all('SELECT i.*, c.label, c.mark, b.name AS bike_name, p.label AS parent_label FROM installations i JOIN components c ON c.id = i.component_id
        LEFT JOIN bikes b ON b.id = i.bike_id LEFT JOIN components p ON p.id = i.parent_component_id
        WHERE i.user_id = ? AND (i.work_session_id = ? OR i.removal_session_id = ?) ORDER BY i.id', [$uid, $ws['id'], $ws['id']]);
    View::render('groupsets/ws', compact('ws', 'created', 'installs'), $ws['title'], 'parts');
}

function page_ws_undo(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    if (Request::isPost()) {
        Inventory::undoSession($uid, $id);
        Session::flash('ok', 'Undone. Parts it added are gone and the old parts are back where they were.');
    }
    redirect('ws', ['id' => $id]);
}

// ------------------------------------------------------------------ spares

function page_spares(): void
{
    $uid = (int)require_user()['id'];
    $spares = Inventory::individualSpares($uid);
    foreach ($spares as &$s) {
        $s['totals'] = Domain::totals($uid, $s);
    }
    unset($s);
    $waiting = Db::all("SELECT c.* FROM components c WHERE c.user_id = ? AND c.status = 'ACTIVE' AND c.disposition = 'AWAITING_SERVICE'
        AND NOT EXISTS (SELECT 1 FROM installations i WHERE i.component_id = c.id AND i.removed_on IS NULL AND i.voided_at IS NULL) ORDER BY c.label", [$uid]);
    $lines = Db::all("SELECT * FROM consumables WHERE user_id = ? AND tracking_mode = 'COUNTED' AND archived_at IS NULL ORDER BY component_type, name", [$uid]);
    foreach ($lines as &$l) {
        $l['stock'] = Inventory::stockLevel($uid, (int)$l['id']);
    }
    unset($l);
    $check = Inventory::spareCheck($uid);
    $shopping = Inventory::shoppingList($uid);
    $sessions = Db::all('SELECT * FROM work_sessions WHERE user_id = ? ORDER BY id DESC LIMIT 10', [$uid]);
    View::render('spares/index', compact('spares', 'waiting', 'lines', 'check', 'shopping', 'sessions'), 'Spares and shopping list', 'parts');
}

function page_stock_take(): void
{
    $uid = (int)require_user()['id'];
    if (!Request::isPost()) {
        redirect('spares');
    }
    $cid = Inventory::drawFromStock($uid, get_int('id'), parse_date(post('on', today()), true), null, nullable(post('label')));
    Session::flash('ok', 'Taken out of stock. It is a part of its own now; install it where it goes.');
    redirect('part_install', ['id' => $cid]);
}

function page_my_settings(): void
{
    $uid = (int)require_user()['id'];
    $types = array_keys(Catalog::raw('stock_units'));
    if (Request::isPost()) {
        $min = [];
        foreach ($types as $t) {
            $v = (string)($_POST['min'][$t] ?? '');
            if ($v !== '' && (!ctype_digit($v) || (int)$v > 99)) {
                throw new UserError('Spares to keep: whole numbers from 0 to 99.');
            }
            if ((int)$v > 0) {
                $min[$t] = (int)$v;
            }
        }
        $spokes = post('spoke_relace_after');
        if (!ctype_digit($spokes) || (int)$spokes > 50) {
            throw new UserError('Broken spokes before a re-lace: a whole number (0 turns it off).');
        }
        UserSettings::set($uid, 'spare_minimums', json_encode($min ?: new stdClass()));
        UserSettings::set($uid, 'spoke_relace_after', (string)(int)$spokes);
        UserSettings::set($uid, 'default_tire_setup', isset(Catalog::raw('tire_setups')[post('default_tire_setup')]) ? post('default_tire_setup') : 'TUBE');
        Session::flash('ok', 'Settings saved.');
        redirect('my_settings');
    }
    View::render('account/settings', ['types' => $types, 'min' => UserSettings::spareMinimums($uid),
        'spokes' => UserSettings::get($uid, 'spoke_relace_after'), 'tire' => UserSettings::get($uid, 'default_tire_setup')], 'My settings', 'account');
}
