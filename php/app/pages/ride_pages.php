<?php
declare(strict_types=1);

// Rides, entered by hand. Removing a ride hides it from all totals but keeps it (can be restored).

function page_rides(): void
{
    $uid = (int)require_user()['id'];
    $bikeId = get_int('bike');
    $removed = get_param('show') === 'removed';
    $page = max(1, get_int('page'));
    $sql = 'FROM rides r LEFT JOIN bikes b ON b.id = r.bike_id WHERE r.user_id = ? AND r.removed_at IS ' . ($removed ? 'NOT NULL' : 'NULL');
    $args = [$uid];
    if ($bikeId) {
        $sql .= ' AND r.bike_id = ?';
        $args[] = $bikeId;
    }
    $count = (int)Db::value("SELECT COUNT(*) $sql", $args);
    $per = 50;
    $rides = Db::all("SELECT r.*, b.name AS bike_name $sql ORDER BY r.ride_date DESC, r.start_time DESC, r.id DESC LIMIT $per OFFSET " . (($page - 1) * $per), $args);
    $sum = Db::one("SELECT COALESCE(SUM(r.distance_km),0) km, COALESCE(SUM(r.duration_s),0) s $sql", $args);
    $change = [];
    foreach (array_unique(array_filter(array_column($rides, 'bike_id'))) as $b) {
        $change[$b] = Domain::changeDays($uid, (int)$b);
    }
    $bikes = Db::all('SELECT id, name, status FROM bikes WHERE user_id = ? ORDER BY name', [$uid]);
    View::render('rides/list', compact('rides', 'bikes', 'bikeId', 'removed', 'page', 'count', 'per', 'sum', 'change'), t('Rides'), 'rides');
}

function page_ride_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $lastBike = Db::value('SELECT bike_id FROM rides WHERE user_id = ? ORDER BY id DESC LIMIT 1', [$uid]);
    $ride = $id ? (Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound(t('Ride not found.')))
        : ['id' => 0, 'bike_id' => get_int('bike') ?: $lastBike, 'ride_date' => today(), 'start_time' => null, 'name' => '', 'distance_km' => null,
            'duration_s' => null, 'elevation_m' => null, 'kind' => 'OUTDOOR', 'conditions' => null, 'notes' => ''];
    if (Request::isPost()) {
        $bikeId = (int)post('bike_id') ?: null;
        if ($bikeId) {
            Domain::bike($uid, $bikeId);
        }
        $time = post('start_time');
        if ($time !== '' && !preg_match('/^\d{2}:\d{2}$/', $time)) {
            throw new UserError(t('Start time: use hh:mm.'));
        }
        $dist = parse_number(post('distance_km'), t('Distance'));
        if ($dist !== null && $dist > 2000) {
            throw new UserError(t('That distance looks too long for one ride.'));
        }
        $elev = parse_number(post('elevation_m'), t('Elevation'));
        $row = [
            'bike_id' => $bikeId, 'ride_date' => parse_date(post('ride_date'), true), 'start_time' => $time === '' ? null : $time . ':00',
            'name' => nullable(mb_substr(post('name'), 0, 200)), 'distance_km' => $dist, 'duration_s' => parse_duration(post('duration')),
            'elevation_m' => $elev === null ? null : (int)$elev, 'kind' => post('kind') === 'INDOOR' ? 'INDOOR' : 'OUTDOOR',
            'conditions' => in_array(post('conditions'), ['DRY', 'WET'], true) ? post('conditions') : null,
            'notes' => nullable(post('notes')), 'updated_at' => now_utc(),
        ];
        if ($row['ride_date'] > (new DateTimeImmutable(today()))->modify('+1 day')->format('Y-m-d')) {
            throw new UserError(t('The ride date is in the future.'));
        }
        if ($id) {
            Db::updateOwned('rides', $id, $uid, $row);
            Session::flash('ok', t('Ride saved. Part km are updated.'));
            if (post('again') !== '1' && $bikeId) {
                Inventory::ensureFrame($uid, $bikeId);
                redirect('ride', ['id' => $id]);
            }
        } else {
            $id = Db::insert('rides', $row + ['user_id' => $uid, 'created_at' => now_utc()]);
            Session::flash('ok', $dist === null ? t('Ride added without a distance (it shows as missing).') : t('Ride added.'));
        }
        if ($bikeId) {
            Inventory::ensureFrame($uid, $bikeId);
        }
        if (post('again') === '1') {
            redirect('ride_edit', ['bike' => $bikeId ?? 0]);
        }
        redirect('rides');
    }
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND (status = 'ACTIVE' OR id = ?) ORDER BY name", [$uid, (int)$ride['bike_id']]);
    View::render('rides/edit', compact('ride', 'bikes'), $id ? t('Edit ride') : t('Add a ride'), 'rides');
}

function page_ride_status(): void
{
    $uid = (int)require_user()['id'];
    $ride = Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound(t('Ride not found.'));
    if (Request::isPost()) {
        if (post('do') === 'remove') {
            Db::updateOwned('rides', (int)$ride['id'], $uid, ['removed_at' => now_utc(), 'updated_at' => now_utc()]);
            Session::flash('ok', t('Ride removed from all totals. You find it under "Removed rides" to restore it.'));
        } else {
            Db::updateOwned('rides', (int)$ride['id'], $uid, ['removed_at' => null, 'updated_at' => now_utc()]);
            Session::flash('ok', t('Ride restored.'));
        }
    }
    redirect('rides');
}

/** One ride: leave out of the km / count again, wheels used on this ride. */
function page_ride_do(): void
{
    $uid = (int)require_user()['id'];
    $ride = Rides::get($uid, get_int('id'));
    if (Request::isPost()) {
        match (post('do')) {
            'exclude' => Rides::exclude($uid, (int)$ride['id'], post('reason')),
            'include' => Rides::include($uid, (int)$ride['id']),
            'equip' => Rides::setEquipment($uid, (int)$ride['id'], post('slot'), post('part')),
            default => throw new UserError(t('Unknown action.')),
        };
        Session::flash('ok', match (post('do')) {
            'exclude' => t('This ride no longer counts for any part. It stays in the list.'),
            'include' => t('This ride counts again.'),
            default => t('Saved. The km of the parts follow.'),
        });
    }
    redirect('ride', ['id' => $ride['id']]);
}

function page_rides_bulk(): void
{
    $uid = (int)require_user()['id'];
    if (Request::isPost()) {
        $do = post('do');
        $n = Rides::bulk($uid, post_list('ids'), $do, (int)post('bike_id') ?: null, post('reason'));
        Session::flash('ok', tn('{n} ride changed.', '{n} rides changed.', $n));
    }
    $back = [];
    foreach (['bike', 'page', 'show'] as $k) {
        if (post("back_$k") !== '') {
            $back[$k] = post("back_$k");
        }
    }
    redirect('rides', $back);
}

function page_ride_import(): void
{
    $uid = (int)require_user()['id'];
    $result = null;
    if (Request::isPost()) {
        $f = $_FILES['file'] ?? null;
        if (!$f || !is_string($f['tmp_name'] ?? null) || $f['error'] !== UPLOAD_ERR_OK) {
            throw new UserError(t('Choose a CSV file.'));
        }
        $result = Rides::importCsv($uid, (string)file_get_contents($f['tmp_name']), post('do') !== 'import');
        $result['file'] = mb_substr(basename((string)$f['name']), 0, 120);
        if (!$result['dry_run']) {
            Session::flash('ok', t('{n} rides added.', ['n' => $result['counts']['CREATED']]));
        }
    }
    View::render('rides/import', ['result' => $result, 'bikes' => array_column(Db::all('SELECT name FROM bikes WHERE user_id = ? ORDER BY name', [$uid]), 'name')],
        t('Import rides (CSV)'), 'rides');
}
