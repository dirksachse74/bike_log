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
    $bikes = Db::all('SELECT id, name FROM bikes WHERE user_id = ? ORDER BY name', [$uid]);
    View::render('rides/list', compact('rides', 'bikes', 'bikeId', 'removed', 'page', 'count', 'per', 'sum', 'change'), 'Rides', 'rides');
}

function page_ride_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $lastBike = Db::value('SELECT bike_id FROM rides WHERE user_id = ? ORDER BY id DESC LIMIT 1', [$uid]);
    $ride = $id ? (Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Ride not found.'))
        : ['id' => 0, 'bike_id' => get_int('bike') ?: $lastBike, 'ride_date' => today(), 'start_time' => null, 'name' => '', 'distance_km' => null,
            'duration_s' => null, 'elevation_m' => null, 'kind' => 'OUTDOOR', 'conditions' => null, 'notes' => ''];
    if (Request::isPost()) {
        $bikeId = (int)post('bike_id') ?: null;
        if ($bikeId) {
            Domain::bike($uid, $bikeId);
        }
        $time = post('start_time');
        if ($time !== '' && !preg_match('/^\d{2}:\d{2}$/', $time)) {
            throw new UserError('Start time: use hh:mm.');
        }
        $dist = parse_number(post('distance_km'), 'Distance');
        if ($dist !== null && $dist > 2000) {
            throw new UserError('That distance looks too long for one ride.');
        }
        $elev = parse_number(post('elevation_m'), 'Elevation');
        $row = [
            'bike_id' => $bikeId, 'ride_date' => parse_date(post('ride_date'), true), 'start_time' => $time === '' ? null : $time . ':00',
            'name' => nullable(mb_substr(post('name'), 0, 200)), 'distance_km' => $dist, 'duration_s' => parse_duration(post('duration')),
            'elevation_m' => $elev === null ? null : (int)$elev, 'kind' => post('kind') === 'INDOOR' ? 'INDOOR' : 'OUTDOOR',
            'conditions' => in_array(post('conditions'), ['DRY', 'WET'], true) ? post('conditions') : null,
            'notes' => nullable(post('notes')), 'updated_at' => now_utc(),
        ];
        if ($row['ride_date'] > (new DateTimeImmutable(today()))->modify('+1 day')->format('Y-m-d')) {
            throw new UserError('The ride date is in the future.');
        }
        if ($id) {
            Db::updateOwned('rides', $id, $uid, $row);
            Session::flash('ok', 'Ride saved. Part km are updated.');
        } else {
            $id = Db::insert('rides', $row + ['user_id' => $uid, 'created_at' => now_utc()]);
            Session::flash('ok', 'Ride added' . ($dist === null ? ' without a distance (it shows as missing).' : '.'));
        }
        if (post('again') === '1') {
            redirect('ride_edit', ['bike' => $bikeId ?? 0]);
        }
        redirect('rides');
    }
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND (status = 'ACTIVE' OR id = ?) ORDER BY name", [$uid, (int)$ride['bike_id']]);
    View::render('rides/edit', compact('ride', 'bikes'), $id ? 'Edit ride' : 'Add a ride', 'rides');
}

function page_ride_status(): void
{
    $uid = (int)require_user()['id'];
    $ride = Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound('Ride not found.');
    if (Request::isPost()) {
        if (post('do') === 'remove') {
            Db::updateOwned('rides', (int)$ride['id'], $uid, ['removed_at' => now_utc(), 'updated_at' => now_utc()]);
            Session::flash('ok', 'Ride removed from all totals. You find it under "Removed rides" to restore it.');
        } else {
            Db::updateOwned('rides', (int)$ride['id'], $uid, ['removed_at' => null, 'updated_at' => now_utc()]);
            Session::flash('ok', 'Ride restored.');
        }
    }
    redirect('rides');
}
