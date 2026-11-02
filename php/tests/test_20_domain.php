<?php
declare(strict_types=1);

// Mileage, installation history and reminders (in-process), then every page once through the web server.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'rider@example.test', 'display_name' => 'Rider', 'password_hash' => Auth::hash('rider-secret-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$other = Db::insert('users', ['email' => 'other@example.test', 'display_name' => 'Other', 'password_hash' => Auth::hash('other-secret-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($other);

$bike = fn(string $name) => Db::insert('bikes', ['user_id' => $uid, 'name' => $name, 'shifting' => 'ELECTRONIC', 'created_at' => $now, 'updated_at' => $now]);
$part = fn(string $type, string $label, string $prior = 'NEW', ?float $start = null) => Db::insert('components', ['user_id' => $uid,
    'component_type' => $type, 'label' => $label, 'prior_usage' => $prior, 'starting_km' => $start, 'created_at' => $now, 'updated_at' => $now]);
$ride = fn(int $b, string $date, ?float $km, string $kind = 'OUTDOOR', ?int $s = 3600) => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $b,
    'ride_date' => $date, 'distance_km' => $km, 'duration_s' => $s, 'kind' => $kind, 'created_at' => $now, 'updated_at' => $now]);
$total = fn(int $id) => Domain::totals($uid, Domain::component($uid, $id))['total_km'];

$synapse = $bike('Synapse');
$bmc = $bike('BMC');

// chain swap: Chain A until 2026-06-01, Chain B from then (start-inclusive, end-exclusive)
$chainA = $part('CHAIN', 'Chain', 'NEW');
Db::run("UPDATE components SET mark = 'A' WHERE id = ?", [$chainA]);
$chainB = $part('CHAIN', 'Chain B', 'NEW');
Domain::install($uid, $chainA, $synapse, null, 'CHAIN', '2026-05-01');
$ride($synapse, '2026-05-10', 50.0);
$ride($synapse, '2026-06-01', 40.0);           // swap day: counts for the chain fitted that day (B)
$ride($synapse, '2026-06-02', 30.0);
Domain::install($uid, $chainB, $synapse, null, 'CHAIN', '2026-06-01');   // replaces A in the slot
check(abs($total($chainA) - 50.0) < 0.01, 'chain A: rides before the swap day');
check(abs($total($chainB) - 70.0) < 0.01, 'chain B: swap-day ride and later');
check(isset(Domain::changeDays($uid, $synapse)['2026-06-01']), 'swap day is flagged for review');
check(Domain::openInstallation($uid, $chainA) === null, 'old chain was removed from the slot');
check(Domain::componentName(Domain::component($uid, $chainA)) === 'Chain [A]', 'name shows the mark');

// chain A moves to the BMC later and keeps its own km
Domain::install($uid, $chainA, $bmc, null, 'CHAIN', '2026-07-01');
$ride($bmc, '2026-07-05', 100.0);
check(abs($total($chainA) - 150.0) < 0.01, 'lifetime km across bikes');

// wheelset → rear wheel → tire: tire km follow the wheelset between bikes; indoor rides do not count for it
$ws = $part('WHEELSET', 'Zipp 303');
$rw = $part('REAR_WHEEL', 'Zipp rear');
$tire = $part('TIRE', 'GP5000', 'RECORDED', 200.0);
Domain::install($uid, $ws, $synapse, null, 'WHEELSET', '2026-08-01');
Domain::install($uid, $rw, null, $ws, 'REAR_WHEEL', '2026-08-01');
Domain::install($uid, $tire, null, $rw, 'TIRE', '2026-08-01');
$ride($synapse, '2026-08-02', 80.0);
$ride($synapse, '2026-08-03', 25.0, 'INDOOR');
check(abs($total($tire) - 280.0) < 0.01, 'tire: starting km + outdoor km via wheel and wheelset');
check(abs($total($chainB) - 175.0) < 0.01, 'chain counts indoor rides');
Domain::install($uid, $ws, $bmc, null, 'WHEELSET', '2026-09-01');
$ride($bmc, '2026-09-02', 60.0);
$ride($synapse, '2026-09-03', 70.0);
check(abs($total($tire) - 340.0) < 0.01, 'tire follows the wheelset to the other bike');
check(Domain::currentBike($uid, $tire)['name'] === 'BMC', 'tire is on the BMC now (via wheelset)');
$on = array_column(Domain::installedOn($uid, $synapse, '2026-08-15'), 'label');
check(in_array('GP5000', $on, true) && in_array('Zipp rear', $on, true), 'what was on the bike on a past date');

// missing distance is not zero
$ride($synapse, '2026-09-04', null);
$t = Domain::totals($uid, Domain::component($uid, $chainB));
check($t['missing_distance'] === 1, 'ride without distance is reported as missing');

// unknown prior use shows "at least"
$pads = $part('BRAKE_PADS', 'Pads front', 'UNKNOWN');
Domain::install($uid, $pads, $synapse, null, 'FRONT_PADS', '2026-09-01');
check(str_starts_with(Domain::totalsLabel(Domain::totals($uid, Domain::component($uid, $pads))), 'at least'), 'unknown prior use: "at least"');

// rules on history
check_throws(fn() => Domain::install($uid, $chainA, $synapse, null, 'CHAIN', '2026-06-15'), 'no back-dating into existing history', 'history');
check_throws(fn() => Domain::install($uid, $tire, null, $tire, 'TIRE', '2026-10-01'), 'a part cannot hang on itself');
check_throws(fn() => Domain::install($uid, $chainA, null, $rw, 'CHAIN', '2026-10-01'), 'chain cannot go on a wheel', 'cannot go on');
check_throws(fn() => Domain::install($other, $chainA, null, null, 'CHAIN', '2026-10-01'), "other user cannot touch this part", 'not found');

// a wrong record is voided, not deleted, and its km disappear
$wrong = Domain::install($uid, $part('SADDLE', 'Saddle'), $synapse, null, 'SADDLE', '2026-05-01');
$saddle = (int)Db::value('SELECT component_id FROM installations WHERE id = ?', [$wrong]);
$before = $total($saddle);
Domain::voidInstallation($uid, $wrong, 'was on the other bike');
check($before > 0 && $total($saddle) == 0.0 && Db::one('SELECT id FROM installations WHERE id = ?', [$wrong]), 'void keeps the record but drops its km');

// km correction
Db::insert('usage_adjustments', ['user_id' => $uid, 'component_id' => $saddle, 'effective_on' => '2026-05-01', 'km' => 500, 'is_estimate' => 1, 'note' => 'old bike', 'created_at' => $now]);
check(str_starts_with(Domain::totalsLabel(Domain::totals($uid, Domain::component($uid, $saddle))), '≈'), 'estimated correction shows ≈');

// ------------------------------------------------------------------ reminders
$_SESSION = [];
$rem = fn(int $cid, string $code) => array_values(array_filter(Reminders::forUser($uid, null, $cid), fn($r) => ($r['rule']['rule_code'] ?? '') === $code))[0] ?? null;

// chain B: hot wax every 500 km (warn 50). It has 175 km (+70 below) since new.
$r = $rem($chainB, 'CHAIN_HOT_WAX');
check($r !== null && $r['status'] === 'OK' && str_contains($r['text'], 'since new'), 'hot wax OK with explanation: ' . ($r['text'] ?? ''));
$ride($synapse, '2026-09-10', 300.0);
$r = $rem($chainB, 'CHAIN_HOT_WAX');
check($r['status'] === 'OVERDUE' && str_contains($r['text'], '545 km') && str_contains($r['text'], 'interval 500 km'), 'hot wax due: ' . $r['text']);
Domain::logMaintenance($uid, ['action_code' => 'WAX_HOT', 'component_id' => $chainB, 'bike_id' => null, 'performed_on' => '2026-09-11',
    'outcome' => null, 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => null]);
$r = $rem($chainB, 'CHAIN_HOT_WAX');
check($r['status'] === 'OK' && str_contains($r['text'], 'since last hot wax on 2026-09-11'), 'logging hot wax resets it: ' . $r['text']);
$r2 = $rem($chainB, 'CHAIN_WEAR_CHECK');
check($r2 !== null && $r2['status'] !== 'OK' || $r2 !== null, 'wear check rule is separate (not reset by waxing)');
check(!str_contains($r2['text'], 'since last'), 'wax did not reset the wear rule');

// snooze hides without logging maintenance
$ride($synapse, '2026-09-12', 600.0);
Db::insert('reminder_snoozes', ['user_id' => $uid, 'component_id' => $chainB, 'rule_code' => 'CHAIN_HOT_WAX', 'until_date' => '2099-01-01', 'created_at' => $now]);
$r = $rem($chainB, 'CHAIN_HOT_WAX');
check($r['status'] === 'SNOOZED' && $r['snoozed_status'] === 'OVERDUE', 'snooze hides a due reminder');
check((int)Db::value("SELECT COUNT(*) FROM maintenance_events WHERE component_id = ? AND action_code = 'WAX_HOT'", [$chainB]) === 1, 'snooze logged no maintenance');

// measurement → outcome from the limits → needs attention until a newer check
$id = Domain::logMaintenance($uid, ['action_code' => 'CHAIN_MEASURE_WEAR', 'component_id' => $chainB, 'bike_id' => null, 'performed_on' => '2026-09-13',
    'outcome' => null, 'measurement_value' => 0.5, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => null]);
check(Db::value('SELECT outcome FROM maintenance_events WHERE id = ?', [$id]) === 'AT_LIMIT', '0.5 % chain wear → at limit');
$att = array_values(array_filter(Reminders::forUser($uid, null, $chainB), fn($r) => $r['status'] === 'ATTENTION'));
check(count($att) === 1 && str_contains($att[0]['text'], 'At limit'), 'bad check result needs attention');
Domain::voidMaintenance($uid, $id, 'wrong chain');
$att = array_values(array_filter(Reminders::forUser($uid, null, $chainB), fn($r) => $r['status'] === 'ATTENTION'));
check(count($att) === 0, 'voided check no longer needs attention');
check_throws(fn() => Domain::logMaintenance($uid, ['action_code' => 'WAX_HOT', 'component_id' => $tire, 'bike_id' => null, 'performed_on' => '2026-09-13',
    'outcome' => null, 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => null]),
    'action must fit the part type', 'does not apply');

// unknown prior use → insufficient information; time-based rule
$r = $rem($pads, 'BRAKE_PAD_CHECK');
check($r !== null && str_starts_with($r['text'], 'Insufficient information'), 'unknown history says insufficient information');

// bike-level rule and mechanical-only rules
$bikeRems = array_filter(Reminders::forUser($uid, $synapse), fn($r) => $r['component'] === null);
check(count($bikeRems) > 0, 'bike-level reminders (torque check, full service)');
$cable = $part('SHIFT_CABLE', 'Cable');
Domain::install($uid, $cable, $synapse, null, 'SHIFT_CABLE_REAR', '2026-09-01');
check(count(Reminders::forUser($uid, null, $cable)) === 0, 'cable rules only for mechanical shifting');
Db::run("UPDATE bikes SET shifting = 'MECHANICAL' WHERE id = ?", [$synapse]);
check(count(Reminders::forUser($uid, null, $cable)) > 0, 'cable rules on a mechanical bike');

// consumables: buy and use (via maintenance) are separate entries
$wax = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'WAX', 'name' => 'Silca hot wax', 'unit' => 'g', 'track_stock' => 1, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $wax, 'kind' => 'BUY', 'qty' => 500, 'happened_on' => '2026-09-01', 'created_at' => $now]);
$ev = Domain::logMaintenance($uid, ['action_code' => 'WAX_HOT', 'component_id' => $chainB, 'bike_id' => null, 'performed_on' => '2026-09-20',
    'outcome' => null, 'measurement_value' => null, 'consumable_id' => $wax, 'consumable_qty' => 30.0, 'cost_cents' => null, 'shop' => null, 'notes' => null]);
check(abs(Domain::stock($uid, $wax) - 470.0) < 0.01, 'using wax in maintenance lowers stock');
Domain::voidMaintenance($uid, $ev, 'test');
check(abs(Domain::stock($uid, $wax) - 500.0) < 0.01, 'voiding the maintenance gives the stock back');

// retire keeps history
Domain::retire($uid, $chainA, '2026-10-01', 'worn');
check(Domain::component($uid, $chainA)['status'] === 'RETIRED' && abs($total($chainA) - 210.0) < 0.01, 'retired part keeps its km');
check(count(Reminders::forUser($uid, null, $chainA)) === 0, 'retired parts have no reminders');

// ------------------------------------------------------------------ every page renders for a user with data
$w = new Browser($base);
$w->post('r=login', ['email' => 'rider@example.test', 'password' => 'rider-secret-pw']);
$pages = ['', 'r=bikes', "r=bike&id=$synapse", "r=bike&id=$synapse&on=2026-08-15", 'r=bike_edit', "r=bike_edit&id=$bmc", 'r=parts', 'r=parts&show=all&type=CHAIN',
    "r=part&id=$chainB", "r=part&id=$tire", "r=part&id=$ws", 'r=part_edit', "r=part_edit&id=$tire", "r=part_install&id=$chainA", 'r=rides', 'r=rides&show=removed',
    'r=ride_edit', 'r=maintenance', 'r=log', "r=log&part=$chainB&action=WAX_HOT", 'r=reminders', 'r=rules', 'r=supplies', 'r=supply_edit', "r=supply&id=$wax",
    'r=account', "r=rule_edit&part=$chainB&code=CHAIN_HOT_WAX"];
foreach ($pages as $p) {
    $w->get($p);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $p renders (status {$w->status})");
}
$w->get("r=part&id=$chainB");
check(str_contains($w->body, 'since last hot wax') || str_contains($w->body, 'Hot wax'), 'part page shows reminders');

// forms through the web
$w->post('r=ride_edit', ['bike_id' => $synapse, 'ride_date' => '2026-10-02', 'distance_km' => '42,5', 'duration' => '1:30', 'kind' => 'OUTDOOR']);
check(Db::one("SELECT * FROM rides WHERE user_id = ? AND distance_km = 42.5 AND duration_s = 5400", [$uid]) !== null, 'ride form (comma decimal, h:mm)');
$w->post('r=part_edit', ['component_type' => 'BRAKE_PADS', 'label' => '', 'maker' => 'Shimano', 'model' => 'L05A', 'prior_usage' => 'NEW',
    'install_bike_id' => $bmc, 'slot' => 'REAR_PADS', 'installed_on' => '2026-10-01']);
$newPads = Db::one("SELECT * FROM components WHERE user_id = ? AND label = 'Shimano L05A'", [$uid]);
check($newPads !== null && Domain::currentBike($uid, (int)$newPads['id'])['id'] == $bmc, 'add part with install in one form');
$w->post('r=log', ['target' => 'c:' . $newPads['id'], 'action_code' => 'PAD_MEASURE', 'performed_on' => '2026-10-02', 'measurement_value' => '0.8']);
check(Db::value("SELECT outcome FROM maintenance_events WHERE component_id = ? ORDER BY id DESC LIMIT 1", [$newPads['id']]) === 'LOW', 'log form with measurement');
$w->post("r=rule_edit&part=$chainB&code=CHAIN_HOT_WAX", ['interval_km' => '400', 'warn_km' => '40', 'origin' => 'PERSONAL', 'active' => '1']);
check(Db::value("SELECT interval_km FROM service_rules WHERE component_id = ? AND rule_code = 'CHAIN_HOT_WAX'", [$chainB]) == 400, 'part-level interval');
check(Db::value("SELECT interval_km FROM service_rules WHERE user_id = ? AND component_type = 'CHAIN' AND rule_code = 'CHAIN_HOT_WAX'", [$uid]) == 500, 'type rule unchanged');

// the other user sees none of it
$o = new Browser($base);
$o->post('r=login', ['email' => 'other@example.test', 'password' => 'other-secret-pw']);
foreach (["r=part&id=$chainB", "r=bike&id=$synapse", "r=supply&id=$wax", "r=log&part=$chainB"] as $p) {
    $o->get($p);
    check($o->status === 404 || !str_contains($o->body, 'Chain B'), "other user cannot see $p");
}
$o->post('r=log', ['target' => 'c:' . $chainB, 'action_code' => 'WAX_HOT', 'performed_on' => '2026-10-02']);
check((int)Db::value("SELECT COUNT(*) FROM maintenance_events WHERE user_id = ?", [$other]) === 0, 'other user cannot log on my part');
$o->get('r=reminders');
check(!str_contains($o->body, 'Synapse'), "other user's reminders are their own");
