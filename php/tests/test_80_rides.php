<?php
declare(strict_types=1);

// Round 5a: rides left out of the km, wheels picked for one ride, several rides at once, CSV import, shoes in use.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'rides5@example.test', 'display_name' => 'Rides', 'password_hash' => Auth::hash('ride-on-and-on-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Roadmachine', 'created_at' => $now, 'updated_at' => $now]);
$bike2 = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Synapse', 'created_at' => $now, 'updated_at' => $now]);
$part = fn(string $type, string $label) => Inventory::createComponent($uid, ['component_type' => $type, 'label' => $label, 'prior_usage' => 'NEW']);
$ride = fn(string $date, float $km, int $b = 0, string $kind = 'OUTDOOR') => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $b ?: $bike, 'ride_date' => $date,
    'distance_km' => $km, 'duration_s' => 3600, 'kind' => $kind, 'created_at' => $now, 'updated_at' => $now]);
$km = fn(int $cid) => Domain::totals($uid, Domain::component($uid, $cid))['total_km'];

$front = $part('FRONT_WHEEL', 'Alu front');
$race = $part('FRONT_WHEEL', 'Carbon front');
$tireA = $part('TIRE', 'Tire on alu');
$tireR = $part('TIRE', 'Tire on carbon');
$chain = $part('CHAIN', 'Chain');
Domain::install($uid, $front, $bike, null, 'FRONT_WHEEL', '2026-04-01');
Domain::install($uid, $tireA, null, $front, 'TIRE', '2026-04-01');
Domain::install($uid, $tireR, null, $race, 'TIRE', '2026-04-01');
Domain::install($uid, $chain, $bike, null, 'CHAIN', '2026-04-01');
$r1 = $ride('2026-04-05', 50);
$r2 = $ride('2026-04-06', 100);
check($km($front) == 150.0 && $km($race) == 0.0, 'normally the fitted wheel counts');

// ------------------------------------------------------------------ race wheels for one ride
Rides::setEquipment($uid, $r2, 'FRONT_WHEEL', (string)$race);
check($km($front) == 50.0 && $km($tireA) == 50.0, 'the fitted wheel and its tire lose that ride');
check($km($race) == 100.0 && $km($tireR) == 100.0, 'the picked wheel and the tire on it get that ride');
check($km($chain) == 150.0, 'other parts are not affected');
$eq = Rides::equipment($uid, Rides::get($uid, $r2));
check(isset($eq['FRONT_WHEEL']) && (int)$eq['FRONT_WHEEL']['set']['component_id'] === $race && !isset($eq['WHEELSET']), 'equipment shows the pick, no wheelset row on a bike with single wheels');
Rides::setEquipment($uid, $r2, 'FRONT_WHEEL', 'none');
check($km($front) == 50.0 && $km($race) == 0.0, '"none": no front wheel gets that ride');
Rides::setEquipment($uid, $r2, 'FRONT_WHEEL', '');
check($km($front) == 150.0, 'back to "as fitted"');
check_throws(fn() => Rides::setEquipment($uid, $r2, 'FRONT_WHEEL', (string)$chain), 'a chain is no wheel', 'does not go');
// the picked wheel's own installed ride is not counted twice
Rides::setEquipment($uid, $r1, 'FRONT_WHEEL', (string)$front);
check($km($front) == 150.0, 'picking the fitted wheel counts the ride once');
Rides::setEquipment($uid, $r1, 'FRONT_WHEEL', '');

// ------------------------------------------------------------------ leave out of the km
Rides::exclude($uid, $r2, 'rented bike');
check($km($chain) == 50.0 && Domain::bikeKm($uid, $bike)['km'] == 50.0, 'a left-out ride gives no km');
check_throws(fn() => Rides::exclude($uid, $r1, ' '), 'a reason is needed', 'why');
Rides::include($uid, $r2);
check($km($chain) == 150.0, 'counted again');
Db::updateOwned('rides', $r2, $uid, ['conditions' => 'WET']);
check(Reminders::wetRidesAfter($uid, Domain::component($uid, $chain), '2026-04-01') === ['2026-04-06'], 'wet rides found through the usage periods');
Rides::exclude($uid, $r2, 'test');
check(Reminders::wetRidesAfter($uid, Domain::component($uid, $chain), '2026-04-01') === [], 'a left-out wet ride does not ask for a top-up');
Rides::include($uid, $r2);

// ------------------------------------------------------------------ several rides at once
$r3 = $ride('2026-04-07', 30, $bike2);
$r4 = $ride('2026-04-08', 20, $bike2);
check(Rides::bulk($uid, [$r3, $r4], 'bike', $bike) === 2 && $km($chain) == 200.0, 'assign a bike to two rides');
check(Rides::bulk($uid, [$r3, $r4, $r3], 'exclude', null, 'duplicates') === 2 && $km($chain) == 150.0, 'leave out two rides');
check(Rides::bulk($uid, [$r3, $r4], 'include') === 2, 'count them again');
check(Rides::bulk($uid, [$r3], 'remove') === 1 && $km($chain) == 170.0, 'remove one');
check(Rides::bulk($uid, [$r3], 'restore') === 1 && $km($chain) == 200.0, 'restore it');
check_throws(fn() => Rides::bulk($uid, [], 'remove'), 'nothing ticked', 'Tick');

// ------------------------------------------------------------------ shoes in use (rider gear)
$shoes = $part('SHOES', 'Shoes');
$cleats = $part('CLEATS', 'Cleats');
Domain::install($uid, $cleats, null, $shoes, 'CLEATS', '2026-04-01');
check($km($shoes) == 0.0, 'shoes not in use count nothing');
Inventory::setInUse($uid, $shoes, true, '2026-04-06');
$r5 = $ride('2026-04-09', 40, $bike2);
check($km($shoes) == 100.0 + 30 + 20 + 40, 'shoes in use: every ride on any bike from that day');
check($km($cleats) == $km($shoes), 'cleats on the shoes count the same');
check(Domain::wornNow($uid, $cleats) && Domain::currentBike($uid, $shoes) === null, 'worn now, on no bike');
Inventory::setInUse($uid, $shoes, false, '2026-04-08');
check($km($shoes) == 100.0 + 30, 'put away: later rides no longer count');
check_throws(fn() => Inventory::setInUse($uid, $shoes, true, '2026-04-07'), 'no change before the last one', 'on or after');
check_throws(fn() => Inventory::setInUse($uid, $chain, true, '2026-04-09'), 'a chain is not worn', 'worn by the rider');
Inventory::setInUse($uid, $shoes, true, '2026-04-09');
$rem = array_filter(Reminders::forUser($uid), fn($r) => $r['component'] && (int)$r['component']['id'] === $cleats);
check((bool)$rem && !empty(array_values($rem)[0]['bike']['rider']), 'cleat reminder shows for worn cleats');

// ------------------------------------------------------------------ CSV import
$csv = "source_id,date,distance_km,duration_min,name,bike,trainer,wet\n"
    . "a1,2026-05-01 07:30,42.5,90,Morning,Roadmachine,,yes\n"
    . "a2,2026-05-02,30,,Zwift,roadmachine,yes,\n"
    . "a3,2026-05-03,abc,,,Roadmachine,,\n"
    . "a4,2026-05-04,,,Unknown bike,Gravel,,\n";
$res = Rides::importCsv($uid, $csv, true);
check($res['counts']['CREATED'] === 3 && $res['counts']['ERROR'] === 1 && (int)Db::value("SELECT COUNT(*) FROM rides WHERE user_id = ? AND source_kind = 'CSV'", [$uid]) === 0,
    'check counts and writes nothing');
$res = Rides::importCsv($uid, $csv);
$a1 = Db::one("SELECT * FROM rides WHERE user_id = ? AND source_ref = 'a1'", [$uid]);
check($a1 && (int)$a1['bike_id'] === $bike && $a1['start_time'] === '07:30:00' && (int)$a1['duration_s'] === 5400 && $a1['conditions'] === 'WET', 'row with bike, time, duration, wet');
check(Db::value("SELECT kind FROM rides WHERE user_id = ? AND source_ref = 'a2'", [$uid]) === 'INDOOR', 'trainer = indoor; bike name ignores case');
check(($res['unknown_bikes']['Gravel'] ?? 0) === 1 && Db::value("SELECT bike_id FROM rides WHERE user_id = ? AND source_ref = 'a4'", [$uid]) === null, 'unknown bike listed, ride without bike');
check(str_contains($res['errors'][0] ?? '', "Row 4: distance_km 'abc' is not a number"), 'error names the row');
Db::updateOwned('rides', (int)$a1['id'], $uid, ['distance_km' => 44]);
$res = Rides::importCsv($uid, $csv);
check($res['counts']['CREATED'] === 0 && $res['counts']['EXISTS'] === 3 && (float)Db::value('SELECT distance_km FROM rides WHERE id = ?', [$a1['id']]) == 44.0,
    'importing again adds nothing and keeps my edits');
$strava = "Activity ID,Activity Date,Activity Name,Activity Type,Elapsed Time,Distance,Activity Gear,Distance\n"
    . "111,\"May 10, 2026, 6:00:00 AM\",Early,Ride,3600,25.5,Synapse,25500\n"
    . "112,\"May 11, 2026, 6:00:00 PM\",Run,Run,1800,5,,5000\n"
    . "113,\"May 12, 2026, 11:30:00 PM\",Zwift,Virtual Ride,3600,30,Synapse,30000\n";
$res = Rides::importCsv($uid, $strava);
$s1 = Db::one("SELECT * FROM rides WHERE user_id = ? AND source_kind = 'STRAVA_CSV' AND source_ref = '111'", [$uid]);
check($res['counts']['CREATED'] === 2 && $res['counts']['SKIPPED'] === 1, 'Strava export: rides in, runs skipped');
check($s1 && $s1['start_time'] === '08:00:00' && (float)$s1['distance_km'] == 25.5 && (int)$s1['bike_id'] === $bike2, 'UTC time shown in my time zone, first Distance column used');
check(Db::value("SELECT ride_date FROM rides WHERE user_id = ? AND source_ref = '113'", [$uid]) === '2026-05-13'
    && Db::value("SELECT kind FROM rides WHERE user_id = ? AND source_ref = '113'", [$uid]) === 'INDOOR', 'late UTC ride lands on the local day; Virtual Ride is indoor');
check_throws(fn() => Rides::importCsv($uid, "foo,bar\n1,2\n"), 'unknown columns refused', 'Unrecognised CSV');
$semi = "source_id;date;distance_km\nb1;2026-06-01;12,5\n";
Rides::importCsv($uid, $semi);
check((float)Db::value("SELECT distance_km FROM rides WHERE user_id = ? AND source_ref = 'b1'", [$uid]) == 12.5, 'semicolon file with decimal comma');

// backups carry ride equipment
Rides::setEquipment($uid, $r2, 'FRONT_WHEEL', (string)$race);
$copy = Db::insert('users', ['email' => 'rides5copy@example.test', 'display_name' => 'C', 'password_hash' => Auth::hash('x-x-x-x-x-x-x-x'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
UserBackups::restore($copy, json_decode(UserBackups::encode(UserBackups::export($uid)), true), 'test');
$raceCopy = (int)Db::value("SELECT id FROM components WHERE user_id = ? AND label = 'Carbon front'", [$copy]);
check(Domain::totals($copy, Domain::component($copy, $raceCopy))['total_km'] == $km($race), 'restore keeps the wheels picked for a ride');

// ------------------------------------------------------------------ pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'rides5@example.test', 'password' => 'ride-on-and-on-pw']);
foreach (['r=rides', "r=ride&id=$r2", "r=ride&id=$r1", 'r=ride_import', "r=part&id=$shoes", "r=part&id=$cleats", 'r=reminders', 'r=home'] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->post("r=ride_do&id=$r1", ['do' => 'exclude', 'reason' => 'double']);
check(Rides::get($uid, $r1)['excluded_reason'] === 'double', 'leave out from the ride page');
$w->post("r=ride_do&id=$r1", ['do' => 'include']);
$w->post("r=ride_do&id=$r1", ['do' => 'equip', 'slot' => 'FRONT_WHEEL', 'part' => (string)$race]);
check((int)Db::value('SELECT component_id FROM ride_equipment WHERE ride_id = ?', [$r1]) === $race, 'wheel picked on the ride page');
$w->post('r=rides_bulk', ['do' => 'bike', 'bike_id' => (string)$bike2, 'ids' => [(string)$r4]]);
check((int)Rides::get($uid, $r4)['bike_id'] === $bike2, 'bulk from the list');
$w->upload('r=ride_import', ['do' => 'import'], ['file' => [['rides.csv', "source_id,date,distance_km\nweb1,2026-07-01,10\n"]]]);
check(str_contains($w->body, '1 added') && (bool)Db::value("SELECT id FROM rides WHERE user_id = ? AND source_ref = 'web1'", [$uid]), 'CSV upload from the page');
$w->post("r=part_in_use&id=$shoes", ['in_use' => '0', 'on' => '2026-07-02']);
check(Domain::component($uid, $shoes)['disposition'] === 'STORED', 'shoes put away from the part page');
$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->post("r=ride_do&id=$r1", ['do' => 'exclude', 'reason' => 'x']);
check($o->status === 404 && Rides::get($uid, $r1)['excluded_reason'] === null, 'other user cannot change my ride');
$o->post('r=rides_bulk', ['do' => 'remove', 'ids' => [(string)$r1]]);
check(Rides::get($uid, $r1)['removed_at'] === null, 'other user cannot bulk-remove my ride');
