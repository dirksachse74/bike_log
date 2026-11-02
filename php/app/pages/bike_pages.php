<?php
declare(strict_types=1);

// Dashboard, bikes and parts.

function page_home(): void
{
    $u = require_user();
    $uid = (int)$u['id'];
    $bikes = Db::all("SELECT * FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    foreach ($bikes as &$b) {
        $b['stats'] = Domain::bikeKm($uid, (int)$b['id']);
    }
    unset($b);
    $all = Reminders::forUser($uid);
    $reminders = array_values(array_filter($all, fn($r) => in_array($r['status'], ['OVERDUE', 'SOON', 'ATTENTION'], true)));
    $unknown = count(array_filter($all, fn($r) => $r['status'] === 'UNKNOWN'));
    $rides = Db::all('SELECT r.*, b.name AS bike_name FROM rides r LEFT JOIN bikes b ON b.id = r.bike_id
        WHERE r.user_id = ? AND r.removed_at IS NULL ORDER BY r.ride_date DESC, r.id DESC LIMIT 5', [$uid]);
    $year = substr(today(), 0, 4);
    $yearKm = (float)Db::value('SELECT COALESCE(SUM(distance_km),0) FROM rides WHERE user_id = ? AND removed_at IS NULL AND ride_date >= ?', [$uid, "$year-01-01"]);
    View::render('dashboard', compact('bikes', 'reminders', 'unknown', 'rides', 'yearKm', 'year'), 'Overview', 'home');
}

function page_bikes(): void
{
    $uid = (int)require_user()['id'];
    $bikes = Db::all('SELECT * FROM bikes WHERE user_id = ? ORDER BY status, name', [$uid]);
    foreach ($bikes as &$b) {
        $b['stats'] = Domain::bikeKm($uid, (int)$b['id']);
    }
    unset($b);
    View::render('bikes/list', compact('bikes'), 'Bikes', 'bikes');
}

function page_bike(): void
{
    $uid = (int)require_user()['id'];
    $bike = Domain::bike($uid, get_int('id'));
    $date = get_param('on') !== '' ? parse_date(get_param('on')) : today();
    $parts = Domain::installedOn($uid, (int)$bike['id'], $date);
    foreach ($parts as &$p) {
        $p['totals'] = Domain::totals($uid, $p);
    }
    unset($p);
    $stats = Domain::bikeKm($uid, (int)$bike['id']);
    $reminders = $bike['status'] === 'ACTIVE' ? Reminders::forUser($uid, (int)$bike['id']) : [];
    $rides = Db::all('SELECT * FROM rides WHERE user_id = ? AND bike_id = ? AND removed_at IS NULL ORDER BY ride_date DESC, id DESC LIMIT 10', [$uid, $bike['id']]);
    $events = Db::all('SELECT e.*, c.label, c.mark FROM maintenance_events e LEFT JOIN components c ON c.id = e.component_id
        WHERE e.user_id = ? AND e.bike_id = ? AND e.voided_at IS NULL ORDER BY e.performed_on DESC, e.id DESC LIMIT 15', [$uid, $bike['id']]);
    $history = Db::all('SELECT i.*, c.label, c.mark, c.component_type FROM installations i JOIN components c ON c.id = i.component_id
        WHERE i.user_id = ? AND i.bike_id = ? ORDER BY COALESCE(i.removed_on, i.installed_on) DESC, i.id DESC LIMIT 40', [$uid, $bike['id']]);
    $changeDays = Domain::changeDays($uid, (int)$bike['id']);
    $incidents = Incidents::list($uid, ['bike_id' => $bike['id'], 'open' => 1]);
    $fixData = fix_data($uid, $incidents);
    $journal = Journal::entries($uid, (int)$bike['id'], null, true);
    View::render('bikes/show', compact('bike', 'parts', 'stats', 'reminders', 'rides', 'events', 'history', 'date', 'changeDays', 'incidents', 'fixData', 'journal'),
        $bike['name'], 'bikes');
}

function page_bike_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $bike = $id ? Domain::bike($uid, $id) : ['id' => 0, 'name' => '', 'maker' => '', 'model' => '', 'year' => '', 'shifting' => '',
        'purchase_date' => '', 'purchase_price_cents' => null, 'notes' => '', 'status' => 'ACTIVE'];
    if (Request::isPost()) {
        $name = post('name');
        if ($name === '' || mb_strlen($name) > 120) {
            throw new UserError('Please give the bike a name (up to 120 characters).');
        }
        $dup = Db::one('SELECT id FROM bikes WHERE user_id = ? AND name = ? AND id <> ?', [$uid, $name, $id]);
        if ($dup) {
            throw new UserError('You already have a bike called ' . $name . '.');
        }
        $year = post('year');
        $row = [
            'name' => $name, 'maker' => nullable(post('maker')), 'model' => nullable(post('model')),
            'year' => $year === '' ? null : (int)$year, 'shifting' => in_array(post('shifting'), ['ELECTRONIC', 'MECHANICAL'], true) ? post('shifting') : null,
            'purchase_date' => parse_date(post('purchase_date')), 'purchase_price_cents' => parse_money_cents(post('purchase_price')),
            'notes' => nullable(post('notes')), 'updated_at' => now_utc(),
        ];
        if ($id) {
            Db::updateOwned('bikes', $id, $uid, $row);
        } else {
            $id = Db::insert('bikes', $row + ['user_id' => $uid, 'created_at' => now_utc()]);
        }
        Inventory::ensureFrame($uid, $id);
        Session::flash('ok', 'Bike saved.');
        redirect('bike', ['id' => $id]);
    }
    View::render('bikes/edit', compact('bike'), $id ? 'Edit ' . $bike['name'] : 'Add a bike', 'bikes');
}

function page_bike_status(): void
{
    $uid = (int)require_user()['id'];
    $bike = Domain::bike($uid, get_int('id'));
    if (!Request::isPost()) {
        redirect('bike', ['id' => $bike['id']]);
    }
    if (post('do') === 'retire') {
        Db::updateOwned('bikes', (int)$bike['id'], $uid, ['status' => 'RETIRED', 'retired_on' => today(), 'updated_at' => now_utc()]);
        Session::flash('ok', 'Bike retired. Its rides and history stay; its parts stay on it until you move them.');
    } elseif (post('do') === 'restore') {
        Db::updateOwned('bikes', (int)$bike['id'], $uid, ['status' => 'ACTIVE', 'retired_on' => null, 'updated_at' => now_utc()]);
        Session::flash('ok', 'Bike is active again.');
    } elseif (post('do') === 'delete') {
        $used = (int)Db::value('SELECT (SELECT COUNT(*) FROM rides WHERE bike_id = ?) + (SELECT COUNT(*) FROM installations WHERE bike_id = ?)
            + (SELECT COUNT(*) FROM maintenance_events WHERE bike_id = ?) + (SELECT COUNT(*) FROM journal_entries WHERE bike_id = ?)
            - (SELECT COUNT(*) FROM installations WHERE bike_id = ? AND note = ? AND removed_on IS NULL AND voided_at IS NULL)',
            [$bike['id'], $bike['id'], $bike['id'], $bike['id'], $bike['id'], Inventory::AUTO_FRAME_NOTE]);
        if ($used > 0) {
            throw new UserError('This bike has rides, parts or maintenance in its history, so it can only be retired, not deleted.');
        }
        Db::tx(function () use ($uid, $bike) {
            $frames = Db::all('SELECT component_id FROM installations WHERE user_id = ? AND bike_id = ? AND note = ?', [$uid, $bike['id'], Inventory::AUTO_FRAME_NOTE]);
            Db::run('DELETE FROM installations WHERE user_id = ? AND bike_id = ?', [$uid, $bike['id']]);
            foreach ($frames as $f) {
                if (!Db::one('SELECT id FROM installations WHERE component_id = ?', [$f['component_id']])) {
                    Db::run('DELETE FROM components WHERE id = ? AND user_id = ?', [$f['component_id'], $uid]);
                }
            }
            Db::run('DELETE FROM bikes WHERE id = ? AND user_id = ?', [$bike['id'], $uid]);
        });
        Session::flash('ok', 'Bike deleted (it had no history).');
        redirect('bikes');
    }
    redirect('bike', ['id' => $bike['id']]);
}

// ------------------------------------------------------------------ parts

function page_parts(): void
{
    $uid = (int)require_user()['id'];
    $filter = get_param('show', 'active');
    $type = get_param('type');
    $sql = 'SELECT * FROM components WHERE user_id = ?';
    $args = [$uid];
    if ($filter !== 'all') {
        $sql .= " AND status = 'ACTIVE'";
    }
    if ($type !== '' && Catalog::type($type)) {
        $sql .= ' AND component_type = ?';
        $args[] = $type;
    }
    $parts = Db::all($sql . ' ORDER BY component_type, label', $args);
    foreach ($parts as &$p) {
        $p['bike'] = Domain::currentBike($uid, (int)$p['id']);
        $p['totals'] = Domain::totals($uid, $p);
    }
    unset($p);
    View::render('parts/list', compact('parts', 'filter', 'type'), 'Parts', 'parts');
}

function page_part(): void
{
    $uid = (int)require_user()['id'];
    $c = Domain::component($uid, get_int('id'));
    $totals = Domain::totals($uid, $c);
    $installs = Domain::installations($uid, (int)$c['id']);
    $open = Domain::openInstallation($uid, (int)$c['id']);
    $bike = Domain::currentBike($uid, (int)$c['id']);
    $children = Db::all('SELECT i.id AS installation_id, i.slot, i.installed_on, c.* FROM installations i JOIN components c ON c.id = i.component_id
        WHERE i.user_id = ? AND i.parent_component_id = ? AND i.removed_on IS NULL AND i.voided_at IS NULL ORDER BY c.label', [$uid, $c['id']]);
    $events = Db::all('SELECT e.*, s.name AS consumable_name FROM maintenance_events e LEFT JOIN consumables s ON s.id = e.consumable_id
        WHERE e.user_id = ? AND e.component_id = ? ORDER BY e.performed_on DESC, e.id DESC', [$uid, $c['id']]);
    $adjustments = Db::all('SELECT * FROM usage_adjustments WHERE user_id = ? AND component_id = ? ORDER BY effective_on DESC', [$uid, $c['id']]);
    $reminders = $c['status'] === 'ACTIVE' && $bike ? Reminders::forUser($uid, null, (int)$c['id']) : [];
    $rules = Reminders::rulesFor($uid, $c);
    $journal = Journal::entries($uid, null, (int)$c['id'], true);
    $spokes = in_array($c['component_type'], ['FRONT_WHEEL', 'REAR_WHEEL'], true) ? Incidents::spokeInfo($uid, $c) : null;
    $spokeStock = $spokes ? Db::all("SELECT id, name FROM consumables WHERE user_id = ? AND tracking_mode = 'COUNTED' AND component_type = 'SPOKES' AND archived_at IS NULL", [$uid]) : [];
    $incidents = Incidents::list($uid, ['component_id' => $c['id']]);
    $dispositions = Db::all('SELECT * FROM component_dispositions WHERE user_id = ? AND component_id = ? ORDER BY effective_on DESC, id DESC', [$uid, $c['id']]);
    $product = $c['product_id'] ? Db::one('SELECT * FROM products WHERE id = ? AND user_id = ?', [$c['product_id'], $uid]) : null;
    View::render('parts/show', compact('c', 'totals', 'installs', 'open', 'bike', 'children', 'events', 'adjustments', 'reminders', 'rules',
        'journal', 'spokes', 'spokeStock', 'incidents', 'dispositions', 'product'),
        Domain::componentName($c), 'parts');
}

function page_part_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $c = $id ? Domain::component($uid, $id) : ['id' => 0, 'component_type' => get_param('type', 'CHAIN'), 'label' => '', 'maker' => '', 'model' => '',
        'mark' => '', 'serial_number' => '', 'prior_usage' => 'NEW', 'starting_km' => null, 'starting_km_estimate' => 0, 'tire_setup' => null,
        'purchase_date' => '', 'price_cents' => null, 'shop' => '', 'notes' => '', 'storage_location' => '', 'pressure_note' => '', 'warranty_until' => ''];
    if (Request::isPost()) {
        $type = $id ? $c['component_type'] : post('component_type');
        if (!Catalog::type($type)) {
            throw new UserError('Please choose a part type.');
        }
        $label = post('label') !== '' ? post('label') : trim(post('maker') . ' ' . post('model'));
        if ($label === '') {
            $label = Catalog::typeName($type);
        }
        $prior = in_array(post('prior_usage'), ['NEW', 'RECORDED', 'UNKNOWN'], true) ? post('prior_usage') : 'UNKNOWN';
        $start = parse_number(post('starting_km'), 'Km before');
        if ($prior === 'RECORDED' && $start === null) {
            throw new UserError('Enter the km it had before, or choose "unknown".');
        }
        $row = [
            'label' => mb_substr($label, 0, 160), 'maker' => nullable(post('maker')), 'model' => nullable(post('model')),
            'mark' => nullable(post('mark')), 'serial_number' => nullable(post('serial_number')), 'prior_usage' => $prior,
            'starting_km' => $prior === 'RECORDED' ? $start : null, 'starting_km_estimate' => post('starting_km_estimate') === '1' ? 1 : 0,
            'tire_setup' => in_array($type, ['FRONT_WHEEL', 'REAR_WHEEL', 'WHEELSET'], true) && in_array(post('tire_setup'), ['TUBE', 'TUBELESS', 'TUBULAR'], true) ? post('tire_setup') : null,
            'purchase_date' => parse_date(post('purchase_date')), 'price_cents' => parse_money_cents(post('price')),
            'shop' => nullable(post('shop')), 'notes' => nullable(post('notes')), 'updated_at' => now_utc(),
            'storage_location' => nullable(mb_substr(post('storage_location'), 0, 160)), 'pressure_note' => nullable(mb_substr(post('pressure_note'), 0, 80)),
            'warranty_until' => parse_date(post('warranty_until')),
        ];
        if ($id) {
            Db::updateOwned('components', $id, $uid, $row);
            Session::flash('ok', 'Part saved.');
            redirect('part', ['id' => $id]);
        }
        $id = Db::tx(function () use ($uid, $row, $type) {
            $id = Db::insert('components', $row + ['user_id' => $uid, 'component_type' => $type, 'created_at' => now_utc()]);
            $bikeId = (int)post('install_bike_id');
            $parentId = (int)post('install_parent_id');
            if ($bikeId || $parentId) {
                Domain::install($uid, $id, $bikeId ?: null, $parentId ?: null, post('slot') ?: Catalog::slots($type)[0],
                    parse_date(post('installed_on'), true));
            }
            if ($type === 'WHEELSET') {
                Inventory::ensureWheels($uid, $id, ($bikeId || $parentId) ? parse_date(post('installed_on'), true) : null);
            }
            return $id;
        });
        Session::flash('ok', 'Part added.');
        redirect('part', ['id' => $id]);
    }
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    View::render('parts/edit', ['c' => $c, 'bikes' => $bikes, 'preBike' => get_int('bike'),
        'parents' => parent_choices($uid, $c['component_type'])], $id ? 'Edit ' . Domain::componentName($c) : 'Add a part', 'parts');
}

/** Parts that this type can hang on (wheels for a tire ...), as id => "Name (on Bike)". */
function parent_choices(int $uid, string $type): array
{
    $pt = Catalog::parentTypes($type);
    if (!$pt) {
        return [];
    }
    $in = implode(',', array_fill(0, count($pt), '?'));
    $rows = Db::all("SELECT * FROM components WHERE user_id = ? AND status = 'ACTIVE' AND component_type IN ($in) ORDER BY label", array_merge([$uid], $pt));
    $out = [];
    foreach ($rows as $r) {
        $b = Domain::currentBike($uid, (int)$r['id']);
        $out[$r['id']] = Domain::componentName($r) . ' (' . Catalog::typeName($r['component_type']) . ($b ? ', on ' . $b['name'] : ', not on a bike') . ')';
    }
    return $out;
}

function page_part_install(): void
{
    $uid = (int)require_user()['id'];
    $c = Domain::component($uid, get_int('id'));
    if (Request::isPost()) {
        $target = post('target');   // "b:12" or "p:34"
        $bikeId = str_starts_with($target, 'b:') ? (int)substr($target, 2) : null;
        $parentId = str_starts_with($target, 'p:') ? (int)substr($target, 2) : null;
        Domain::install($uid, (int)$c['id'], $bikeId, $parentId, post('slot'), parse_date(post('installed_on'), true), nullable(post('note')),
            true, null, isset(Inventory::dispositions()[post('old_outcome')]) ? post('old_outcome') : null);
        Inventory::ensureWheels($uid, (int)$c['id'], parse_date(post('installed_on'), true));
        Session::flash('ok', 'Installed. Rides from ' . post('installed_on') . ' on count for this part.');
        redirect('part', ['id' => $c['id']]);
    }
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    View::render('parts/install', ['c' => $c, 'bikes' => $bikes, 'parents' => parent_choices($uid, $c['component_type']),
        'open' => Domain::openInstallation($uid, (int)$c['id'])], 'Install ' . Domain::componentName($c), 'parts');
}

function page_inst_remove(): void
{
    $uid = (int)require_user()['id'];
    $i = Db::one('SELECT * FROM installations WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound('Record not found.');
    if (Request::isPost()) {
        $outcome = post('outcome');
        if ($outcome !== '' && isset(Inventory::dispositions()[$outcome])) {
            Inventory::removeWithOutcome($uid, (int)$i['id'], parse_date(post('removed_on'), true), $outcome, nullable(post('reason')));
        } else {
            Domain::remove($uid, (int)$i['id'], parse_date(post('removed_on'), true), nullable(post('reason')));
        }
        Session::flash('ok', 'Removed. Rides from ' . post('removed_on') . ' on no longer count for this part.');
    }
    redirect('part', ['id' => $i['component_id']]);
}

function page_inst_void(): void
{
    $uid = (int)require_user()['id'];
    $i = Db::one('SELECT * FROM installations WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound('Record not found.');
    if (Request::isPost()) {
        Domain::voidInstallation($uid, (int)$i['id'], post('reason'));
        Session::flash('ok', 'Record marked as wrong. It stays in the history but no longer counts.');
    }
    redirect('part', ['id' => $i['component_id']]);
}

function page_part_status(): void
{
    $uid = (int)require_user()['id'];
    $c = Domain::component($uid, get_int('id'));
    if (Request::isPost()) {
        if (post('do') === 'retire') {
            Domain::retire($uid, (int)$c['id'], parse_date(post('retired_on'), true), nullable(post('reason')));
            Session::flash('ok', 'Part retired. Its history and km stay.');
        } elseif (post('do') === 'restore') {
            Db::updateOwned('components', (int)$c['id'], $uid, ['status' => 'ACTIVE', 'retired_on' => null, 'retire_reason' => null, 'updated_at' => now_utc()]);
            Session::flash('ok', 'Part is active again.');
        } elseif (post('do') === 'disposition') {
            if (Domain::openInstallation($uid, (int)$c['id'])) {
                throw new UserError('Remove it from where it is first; then say what happened to it.');
            }
            Inventory::setDisposition($uid, (int)$c['id'], post('disposition'), parse_date(post('on'), true), nullable(post('note')));
            Session::flash('ok', 'Saved.');
        }
    }
    redirect('part', ['id' => $c['id']]);
}

function page_adjust(): void
{
    $uid = (int)require_user()['id'];
    $c = Domain::component($uid, get_int('id'));
    if (Request::isPost()) {
        if (post('do') === 'void') {
            Db::run('UPDATE usage_adjustments SET voided_at = ? WHERE id = ? AND user_id = ? AND component_id = ?', [now_utc(), (int)post('adj'), $uid, $c['id']]);
            Session::flash('ok', 'Correction voided.');
        } else {
            $kmv = parse_number(post('km'), 'Km', true);
            if ($kmv === null || $kmv == 0.0) {
                throw new UserError('Enter the km to add (or a negative number to take away).');
            }
            if (post('note') === '') {
                throw new UserError('Please say why (for example: rides on a borrowed bike).');
            }
            Db::insert('usage_adjustments', ['user_id' => $uid, 'component_id' => $c['id'], 'effective_on' => parse_date(post('effective_on'), true),
                'km' => $kmv, 'is_estimate' => post('is_estimate') === '1' ? 1 : 0, 'note' => post('note'), 'created_at' => now_utc()]);
            Session::flash('ok', 'Km correction saved.');
        }
    }
    redirect('part', ['id' => $c['id']]);
}
