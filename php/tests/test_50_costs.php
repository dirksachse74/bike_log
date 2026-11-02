<?php
declare(strict_types=1);

// Round 3b: bike costs, purchase bundles, sending a part away for repair, part life report, pace forecast.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'costs@example.test', 'display_name' => 'Costs', 'password_hash' => Auth::hash('money-matters-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$_SESSION = [];
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Synapse', 'shifting' => 'ELECTRONIC', 'purchase_date' => '2026-01-10',
    'purchase_price_cents' => 300000, 'created_at' => $now, 'updated_at' => $now]);
Inventory::ensureFrame($uid, $bike);
$part = fn(string $type, string $label, ?int $price = null) => Inventory::createComponent($uid, ['component_type' => $type, 'label' => $label,
    'prior_usage' => 'NEW', 'price_cents' => $price, 'purchase_date' => '2026-01-10']);
$ride = fn(string $date, float $km) => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $bike, 'ride_date' => $date, 'distance_km' => $km,
    'duration_s' => 3600, 'kind' => 'OUTDOOR', 'created_at' => $now, 'updated_at' => $now]);

// ------------------------------------------------------------------ costs
$chain = $part('CHAIN', 'Chain', 3500);
Domain::install($uid, $chain, $bike, null, 'CHAIN', '2026-01-10');
$saddle = $part('SADDLE', 'Saddle');
Domain::install($uid, $saddle, $bike, null, 'SADDLE', '2026-01-10');
$c = Costs::bike($uid, $bike);
check($c['initial'] === 300000 && $c['parts'] === 3500 && $c['running'] === 3500, 'initial = bike price, parts counted once');
check(in_array('Saddle', $c['unpriced'], true) && !in_array('Synapse frame', $c['unpriced'], true), 'unpriced part listed; the frame came with the bike');

// bundle: two parts bought together
$rd = $part('REAR_DERAILLEUR', 'RD');
$fd = $part('FRONT_DERAILLEUR', 'FD');
Domain::install($uid, $rd, $bike, null, 'REAR_DERAILLEUR', '2026-02-01');
Domain::install($uid, $fd, $bike, null, 'FRONT_DERAILLEUR', '2026-02-01');
check_throws(fn() => Bundles::create($uid, 'Bad', [$chain], null, null, 1000, null), 'a priced part cannot join a bundle', 'own price');
$bid = Bundles::create($uid, 'Derailleurs', [$rd, $fd], 'Bike shop', '2026-02-01', 60000, null);
$c = Costs::bike($uid, $bike);
check($c['bundles'] === 60000 && $c['running'] === 63500, 'bundle counts once with its price');
$rows = Bundles::rows($uid);
check(count($rows) === 1 && $rows[0]['bike_id'] === $bike && array_sum($rows[0]['shares']) === 60000, 'bundle row: bike and shares adding up to the price');
check_throws(fn() => Bundles::create($uid, 'Twice', [$rd], null, null, 100, null), 'a part is in one bundle only', 'another bundle');
Bundles::void($uid, $bid, 'typo');
check(Costs::bike($uid, $bike)['bundles'] === 0, 'voided bundle no longer counts');

// stock used: valued at the average purchase price (estimate)
$tubes = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'OTHER', 'tracking_mode' => 'COUNTED', 'component_type' => 'INNER_TUBE', 'name' => 'Tubes',
    'unit' => 'tube', 'track_stock' => 1, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $tubes, 'kind' => 'BUY', 'qty' => 4, 'cost_cents' => 2000, 'happened_on' => '2026-01-10', 'created_at' => $now]);
$wheel = $part('REAR_WHEEL', 'Rear wheel', 40000);
Domain::install($uid, $wheel, $bike, null, 'REAR_WHEEL', '2026-01-10');
$tube = Inventory::drawFromStock($uid, $tubes, '2026-03-01');
Domain::install($uid, $tube, null, $wheel, 'TUBE', '2026-03-01');
$c = Costs::bike($uid, $bike);
check($c['stock'] === 500 && $c['estimated'], 'tube from stock costs 5.00 (estimated)');
check(!in_array(Domain::component($uid, $tube)['label'], $c['unpriced'], true), 'a tube from stock is not "missing a price"');
// service cost
Domain::logMaintenance($uid, ['action_code' => 'FULL_SERVICE', 'component_id' => null, 'bike_id' => $bike, 'performed_on' => '2026-03-02', 'outcome' => null,
    'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => 4500, 'shop' => 'Shop', 'notes' => null]);
$c = Costs::bike($uid, $bike);
check($c['services'] === 4500, 'service cost counts for the bike');

// ------------------------------------------------------------------ send away for repair
$ride('2026-03-05', 50.0);
$o = ServiceOrders::send($uid, $wheel, '2026-03-10', 'Wheel builder', 'hub play');
check(Domain::openInstallation($uid, $wheel) === null && Domain::component($uid, $wheel)['disposition'] === 'AWAITING_SERVICE', 'sent away: off the bike, awaiting repair');
check(Domain::currentBike($uid, $tube) === null, 'the tube went along with the wheel');
$ride('2026-03-12', 40.0);
$before = Domain::totals($uid, Domain::component($uid, $wheel))['total_km'];
check(abs($before - 50.0) < 0.01, 'no km while away');
check_throws(fn() => ServiceOrders::send($uid, $wheel, '2026-03-11', null, null), 'cannot send twice', 'already away');
check_throws(fn() => ServiceOrders::back($uid, $o, '2026-03-10', 'REPAIRED_PAID', 100, null, null), 'must come back after it was sent', 'later');
$r = ServiceOrders::back($uid, $o, '2026-03-20', 'REPAIRED_PAID', 3000, 'R-1', null, true);
check(Domain::currentBike($uid, $wheel)['id'] == $bike && $r['placed'] === 'back on', 'repaired wheel is back on the bike');
check(Costs::bike($uid, $bike)['services'] >= 3000, 'repair cost counts for the bike');
// undo the return: away again; undo the send: as if never sent
Inventory::undoSession($uid, (int)$r['work_session_id']);
check(ServiceOrders::get($uid, $o)['status'] === 'OUT' && Domain::openInstallation($uid, $wheel) === null, 'undo the return: away again');
$r = ServiceOrders::back($uid, $o, '2026-03-21', 'REPLACED_WARRANTY', null, 'RMA 7', null, true, 'STORED', 'Rear wheel (new)', 'SN9', '2028-03-21');
$new = Domain::component($uid, (int)$r['replacement_id']);
$old = Domain::component($uid, $wheel);
check($old['status'] === 'RETIRED' && $old['disposition'] === 'WARRANTY_RETURN', 'warranty: the old wheel is returned and keeps its km');
check(Domain::currentBike($uid, (int)$new['id'])['id'] == $bike && $new['serial_number'] === 'SN9' && $new['warranty_until'] === '2028-03-21', 'warranty: the new wheel is on, with serial and warranty');
check(count(ServiceOrders::rows($uid, ['component_id' => $new['id']])) === 1, 'the new part shows the order that brought it');
check_throws(fn() => ServiceOrders::back($uid, $o, '2026-03-22', 'REPAIRED_PAID', null, null, null), 'cannot come back twice', 'not away');

// incident linked to a repair is solved by it
$ride2 = $ride('2026-03-25', 30.0);
$rd2 = $part('REAR_DERAILLEUR', 'RD2');
Domain::install($uid, $rd2, $bike, null, 'REAR_DERAILLEUR', '2026-03-24');
$g = Incidents::log($uid, $ride2, 'SHIFTING', ['c' . $rd2], 'skips', null);
$o2 = ServiceOrders::send($uid, $rd2, '2026-03-26', 'Shop', 'skipping', $g);
ServiceOrders::back($uid, $o2, '2026-03-28', 'REPAIRED_WARRANTY', null, null, null, true);
check(Incidents::list($uid, ['ride_id' => $ride2])[0]['resolved_on'] === '2026-03-28', 'the repair solved the incident');
$o3 = ServiceOrders::send($uid, $rd2, '2026-04-01', null, null);
Inventory::undoSession($uid, (int)ServiceOrders::get($uid, $o3)['send_session_id']);
check(ServiceOrders::get($uid, $o3)['status'] === 'VOIDED' && Domain::openInstallation($uid, $rd2) !== null, 'undo the send: as if never sent');

// ------------------------------------------------------------------ part life
$bike3 = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Old bike', 'shifting' => 'MECHANICAL', 'created_at' => $now, 'updated_at' => $now]);
$c1 = $part('CHAIN', 'Old chain');
Domain::install($uid, $c1, $bike3, null, 'CHAIN', '2026-01-01');
$c1b = $part('CHAIN', 'Newer chain');
Domain::install($uid, $c1b, $bike3, null, 'CHAIN', '2026-01-10');
Inventory::setDisposition($uid, $c1, 'DISCARDED', '2026-01-11', 'worn');
$life = PartLife::report($uid, 'CHAIN');
check(count($life) === 1 && count($life[0]['finished']) === 1 && $life[0]['finished'][0]['ended'] === '2026-01-10', 'part life: finished chain ended when it came off');
check(count($life[0]['in_use']) === 2 && $life[0]['overall']['count'] === 1, 'part life: the chain in use is listed apart');

// ------------------------------------------------------------------ forecast
$rule = ['interval_km' => 1000.0, 'interval_hours' => null];
$c2 = Domain::component($uid, $chain);
$today = new DateTimeImmutable(today());
foreach ([20, 14, 7, 1] as $d) {
    $ride($today->modify("-$d days")->format('Y-m-d'), 70.0);
}
$f = Reminders::forecast($uid, $c2, $rule, 100.0, 0.0, null);
check($f !== null && str_starts_with($f, 'Due around'), 'forecast at the recent pace');
check(str_contains((string)Reminders::forecast($uid, $c2, $rule, 100.0, 0.0, $today->format('Y-m-d')), 'No forecast yet'), 'no forecast without enough rides');
check(Reminders::forecast($uid, $c2, $rule, 1200.0, 0.0, null) === null, 'no forecast when already due');

// ------------------------------------------------------------------ pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'costs@example.test', 'password' => 'money-matters-pw']);
foreach (["r=costs&bike=$bike", 'r=bundles', 'r=bundles&show=all', 'r=repairs', 'r=part_life', 'r=part_life&type=CHAIN', "r=part&id=$wheel",
    "r=part&id={$new['id']}", "r=part&id=$rd2", "r=bike&id=$bike", 'r=parts', 'r=reminders', "r=groupset&tpl=SRAM_FORCE_AXS_2X12&bike=$bike"] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->get("r=costs&bike=$bike");
check(str_contains($w->body, '3,000.00') || str_contains($w->body, '3.000,00') || str_contains($w->body, '3 000') || str_contains($w->body, '3000'), 'costs page shows the purchase price');
$w->post('r=bundle_do', ['do' => 'create', 'name' => 'Pair', 'price' => '12,50', 'parts' => [$rd, $fd]]);
check((int)Db::value("SELECT price_cents FROM purchase_bundles WHERE user_id = ? AND name = 'Pair'", [$uid]) === 1250, 'bundle through the web');
$w->post("r=repair_send&id=$saddle", ['on' => '2026-04-02', 'shop' => 'Saddle doctor', 'reason' => 'torn']);
$so = ServiceOrders::openFor($uid, $saddle);
check($so !== null, 'send away through the web');
$w->post("r=repair_back&id={$so['id']}", ['on' => '2026-04-05', 'outcome' => 'NOT_REPAIRED', 'keep_as' => 'DISCARDED']);
check(Domain::component($uid, $saddle)['disposition'] === 'DISCARDED', 'back, not repaired, discarded');
$before = (int)Db::value('SELECT COUNT(*) FROM components WHERE user_id = ?', [$uid]);
$w->post('r=groupset', ['tpl' => 'SHIMANO_105_R7100', 'bike_id' => '', 'on' => '2026-04-06', 'occupied' => 'KEEP', 'prior' => 'NEW', 'prefix' => '105',
    'picked' => '1', 'include' => ['chain', 'cassette'], 'bundle_price' => '80', 'merchant' => 'Online', 'do' => 'import']);
$gb = Db::one("SELECT * FROM purchase_bundles WHERE user_id = ? AND price_cents = 8000", [$uid]);
check($gb && count(Bundles::members($uid, (int)$gb['id'])) === 2 && (int)Db::value('SELECT COUNT(*) FROM components WHERE user_id = ?', [$uid]) === $before + 2, 'groupset bought as one bundle');
Inventory::undoSession($uid, (int)$gb['work_session_id']);
check(Db::value('SELECT voided_at FROM purchase_bundles WHERE id = ?', [$gb['id']]) !== null, 'undoing the import voids its bundle');

$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->get("r=costs&bike=$bike");
check($o->status === 404, 'other user cannot see my costs');
$o->post("r=repair_send&id=$chain", ['on' => '2026-04-02']);
check(ServiceOrders::openFor($uid, $chain) === null, 'other user cannot send my part away');
$o->post('r=bundle_do', ['do' => 'void', 'id' => $bid, 'reason' => 'x']);
$o->get('r=bundles');
check(!str_contains($o->body, 'Derailleurs'), 'other user sees no bundles of mine');
