<?php
declare(strict_types=1);

// Round 5b: replace a part (spare, stock, same product, new; parts on it move over), wheels into a wheelset,
// product fits a bike, brake overview, symptom / work done, restore an entry, charge history.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'workshop@example.test', 'display_name' => 'Workshop', 'password_hash' => Auth::hash('workshop-tester-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Synapse', 'created_at' => $now, 'updated_at' => $now]);
$bike2 = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Cube', 'created_at' => $now, 'updated_at' => $now]);
$part = fn(string $type, string $label, ?int $pid = null) => Inventory::createComponent($uid, ['component_type' => $type, 'label' => $label, 'prior_usage' => 'NEW', 'product_id' => $pid]);
$ride = fn(string $date, float $km, int $b = 0, int $secs = 3600) => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $b ?: $bike, 'ride_date' => $date,
    'distance_km' => $km, 'duration_s' => $secs, 'kind' => 'OUTDOOR', 'created_at' => $now, 'updated_at' => $now]);
$km = fn(int $cid) => Domain::totals($uid, Domain::component($uid, $cid))['total_km'];
$on = function (int $cid) use ($uid) {
    $i = Domain::openInstallation($uid, $cid);
    return $i ? [$i['bike_id'] ? 'b' . $i['bike_id'] : 'p' . $i['parent_component_id'], $i['slot']] : null;
};

// ------------------------------------------------------------------ replace a chain with a spare; the quick link moves over
$pChain = Inventory::productFor($uid, 'CHAIN', 'Shimano', 'CN-M8100');
$chainA = $part('CHAIN', 'Chain A', $pChain);
$link = $part('QUICK_LINK', 'Connex link');
Domain::install($uid, $chainA, $bike, null, 'CHAIN', '2026-03-01');
Domain::install($uid, $link, null, $chainA, 'QUICK_LINK', '2026-03-01');
$ride('2026-03-10', 100);
$chainB = $part('CHAIN', 'Chain B', $pChain);
Workshop::setFit($uid, $pChain, $bike, true, 'checked length');
$o = Workshop::replaceOptions($uid, $chainA);
check(count($o['spares']) === 1 && $o['spares'][0]['fit'] === 'VERIFIED', 'the spare chain is offered, marked as fitting (checked)');
check($o['children'][0]['id'] == $link && $o['children'][0]['carry'] === true, 'the quick link moves over by default (it has served one chain)');
check($o['suggested_outcome'] === Inventory::defaultOutcome('CHAIN'), 'what happens to the old chain is preselected');
$res = Workshop::replace($uid, $chainA, '2026-03-20', 'spare:' . $chainB, [], 'STORED', [$link], 'stretched');
check($on($chainB) === ['b' . $bike, 'CHAIN'] && $on($chainA) === null, 'the spare is on, the old chain is off');
check($on($link) === ['p' . $chainB, 'QUICK_LINK'], 'the quick link is on the new chain');
check(Domain::component($uid, $chainA)['disposition'] === 'STORED', 'the old chain is stored');
check((string)Db::value('SELECT removal_reason FROM installations WHERE component_id = ? AND removed_on IS NOT NULL', [$chainA]) === 'stretched', 'the reason is kept');
$ride('2026-03-25', 40);
check($km($chainA) == 100.0 && $km($chainB) == 40.0 && $km($link) == 140.0, 'km: each chain its own, the link both');
check(count(Reminders::parentsServed($uid, $link)) === 2, 'the quick link has served two chains');
// the link has served two chains now: a further replace leaves it behind by default
$o = Workshop::replaceOptions($uid, $chainB);
check($o['children'][0]['carry'] === false && $o['children'][0]['note'] !== null, 'a quick link due for replacement stays behind by default');

// undo puts everything back
Inventory::undoSession($uid, $res['work_session_id']);
check($on($chainA) === ['b' . $bike, 'CHAIN'] && $on($chainB) === null && $on($link) === ['p' . $chainA, 'QUICK_LINK'], 'undo puts the old chain and link back');
check(Domain::component($uid, $chainA)['disposition'] === 'STORED' && $km($chainA) == 140.0, 'undo: the old chain counts again');

// ------------------------------------------------------------------ same product, new item, from stock
$res = Workshop::replace($uid, $chainA, '2026-03-21', 'same', [], 'DISCARDED', []);
$n = Domain::component($uid, $res['new_component_id']);
check((int)$n['product_id'] === $pChain && $n['label'] !== 'Chain A' && $n['purchase_date'] === '2026-03-21', 'same product: a new chain of that product with its own name');
check(Domain::component($uid, $chainA)['status'] === 'RETIRED' && $on($link) === ['p' . $chainA, 'QUICK_LINK'],
    'discarded old chain; an unticked link stays with it');
Inventory::undoSession($uid, $res['work_session_id']);
check(!Db::one('SELECT id FROM components WHERE id = ?', [$res['new_component_id']]) && Domain::component($uid, $chainA)['status'] === 'ACTIVE', 'undo removes the new chain and brings the old one back');

$res = Workshop::replace($uid, $chainA, '2026-03-22', 'new', ['label' => 'KMC X11', 'price_cents' => 2999]);
check(Domain::component($uid, $res['new_component_id'])['label'] === 'KMC X11' && (int)Domain::component($uid, $res['new_component_id'])['price_cents'] === 2999, 'new item with name and price');
Inventory::undoSession($uid, $res['work_session_id']);

$line = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'PART', 'name' => 'Chains in the box', 'unit' => 'pcs', 'tracking_mode' => 'COUNTED', 'component_type' => 'CHAIN',
    'product_id' => $pChain, 'track_stock' => 1, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $line, 'kind' => 'BUY', 'qty' => 2, 'happened_on' => '2026-01-01', 'created_at' => $now]);
$o = Workshop::replaceOptions($uid, $chainA);
check(count($o['stock']) === 1 && $o['stock'][0]['fit'] === 'VERIFIED', 'stock line offered with its fit');
$res = Workshop::replace($uid, $chainA, '2026-03-23', 'stock:' . $line, [], null, [$link]);
check(Inventory::stockLevel($uid, $line) == 1.0 && $on($res['new_component_id']) === ['b' . $bike, 'CHAIN'], 'one chain taken from stock and fitted');
Inventory::undoSession($uid, $res['work_session_id']);
check(Inventory::stockLevel($uid, $line) == 2.0, 'undo gives the stock back');

check_throws(fn() => Workshop::replace($uid, $chainA, '2026-03-24', 'spare:' . $chainA), 'the same part is refused', 'different part');
check_throws(fn() => Workshop::replace($uid, $chainA, '2026-02-01', 'same'), 'a date before the fitting is refused', 'must be later');
check_throws(fn() => Workshop::replace($uid, $chainB, '2026-04-01', 'same'), 'a part that is not fitted cannot be replaced', 'not installed');
check_throws(fn() => Workshop::replace($uid, $chainA, '2026-03-24', 'same', [], null, [$chainB]), 'only parts on the old part can move', 'Only parts');

// ------------------------------------------------------------------ wheels into a wheelset, then replace the wheelset
$fw = $part('FRONT_WHEEL', 'Front 1');
$rw = $part('REAR_WHEEL', 'Rear 1');
$tire = $part('TIRE', 'GP5000 front');
$cass = $part('CASSETTE', 'Ultegra 11-30');
Domain::install($uid, $fw, $bike, null, 'FRONT_WHEEL', '2026-03-01');
Domain::install($uid, $rw, $bike, null, 'REAR_WHEEL', '2026-03-01');
Domain::install($uid, $tire, null, $fw, 'TIRE', '2026-03-01');
Domain::install($uid, $cass, null, $rw, 'CASSETTE', '2026-03-01');
check(count(Workshop::looseWheels($uid, $bike)) === 2, 'two wheels sit directly on the bike');
$g = Workshop::groupWheels($uid, $bike, '2026-04-01', 'Alu set');
check($on($g['wheelset_id']) === ['b' . $bike, 'WHEELSET'] && $on($fw) === ['p' . $g['wheelset_id'], 'FRONT_WHEEL'] && $on($rw) === ['p' . $g['wheelset_id'], 'REAR_WHEEL'],
    'the wheels are in the new wheelset on the bike');
check($on($tire) === ['p' . $fw, 'TIRE'] && Workshop::looseWheels($uid, $bike) === [], 'the tire stays on its wheel');
check((int)Db::value('SELECT COUNT(*) FROM installations WHERE user_id = ? AND parent_component_id = ? AND removed_on IS NULL AND voided_at IS NULL', [$uid, $g['wheelset_id']]) === 2,
    'no extra wheel records are made');
$ride('2026-04-05', 60);
check($km($g['wheelset_id']) == 60.0 && $km($fw) == 200.0 && $km($tire) == 200.0, 'the wheelset counts from the day; wheels and tire carry on');
check_throws(fn() => Workshop::groupWheels($uid, $bike, '2026-04-06'), 'no loose wheels left', 'no wheels');

// replace the wheelset with a spare wheelset that has its own wheels: those positions stay on the old set
$set2 = $part('WHEELSET', 'Carbon set');
Inventory::ensureWheels($uid, $set2, '2026-01-01');
$o = Workshop::replaceOptions($uid, $g['wheelset_id']);
check(count($o['spares']) === 1 && count($o['spares'][0]['mounted']) === 2, 'the spare wheelset shows its own wheels');
$res = Workshop::replace($uid, $g['wheelset_id'], '2026-04-10', 'spare:' . $set2, [], 'STORED', [$fw, $rw]);
check($res['carried'] === 0 && count($res['left_on_old']) === 2 && $on($fw) === ['p' . $g['wheelset_id'], 'FRONT_WHEEL'], 'the old wheels stay in the old set (the new set has its own)');
check($on($set2) === ['b' . $bike, 'WHEELSET'], 'the carbon set is on');
Inventory::undoSession($uid, $res['work_session_id']);
// a new wheelset: the wheels move over, so no empty wheel records are added
$res = Workshop::replace($uid, $g['wheelset_id'], '2026-04-10', 'new', ['label' => 'Alu set 2'], 'STORED', [$fw, $rw]);
check($on($fw) === ['p' . $res['new_component_id'], 'FRONT_WHEEL'] && (int)Db::value('SELECT COUNT(*) FROM installations WHERE parent_component_id = ? AND voided_at IS NULL',
    [$res['new_component_id']]) === 2, 'wheels moved to the new wheelset, no extra wheel records');
Inventory::undoSession($uid, $res['work_session_id']);

// group into an existing spare wheelset (without wheels)
$fw2 = $part('FRONT_WHEEL', 'Front 2');
Domain::install($uid, $fw2, $bike2, null, 'FRONT_WHEEL', '2026-03-01');
$empty = $part('WHEELSET', 'Empty set');
check(array_column(Workshop::wheelsetChoices($uid, $bike2), 'id') == [$empty], 'only the wheelset with room is offered');
$g2 = Workshop::groupWheels($uid, $bike2, '2026-04-01', null, $empty);
check($g2['wheelset_id'] === $empty && $on($fw2) === ['p' . $empty, 'FRONT_WHEEL'], 'grouped into the existing wheelset');
Inventory::undoSession($uid, $g2['work_session_id']);
check($on($fw2) === ['b' . $bike2, 'FRONT_WHEEL'] && $on($empty) === null, 'undo of the grouping');

// ------------------------------------------------------------------ fits
check(count(Workshop::fits($uid, $pChain)) === 1, 'fit listed for the product');
Workshop::setFit($uid, $pChain, $bike, false, null);
check(Workshop::fitFor($uid, $pChain, $bike) === 'UNVERIFIED' && Workshop::fits($uid, $pChain)[0]['note'] === null, 'a fit can be changed to "not checked"');
check(Workshop::fitFor($uid, $pChain, $bike2, $pChain) === 'SAME_PRODUCT' && Workshop::fitFor($uid, $pChain, $bike2) === 'UNKNOWN', 'same product / unknown');
Workshop::removeFit($uid, $pChain, $bike);
check(Workshop::fits($uid, $pChain) === [], 'fit removed');
Workshop::setFit($uid, $pChain, $bike, true, 'ok');

// ------------------------------------------------------------------ brakes: symptom and work done, restore
$brake = $part('BRAKE_CIRCUIT', 'Rear brake');
Domain::install($uid, $brake, $bike, null, 'REAR_BRAKE', '2026-03-01');
$oil = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'BRAKE_FLUID', 'name' => 'Mineral oil', 'unit' => 'ml', 'tracking_mode' => 'BULK', 'track_stock' => 1, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $oil, 'kind' => 'BUY', 'qty' => 100, 'happened_on' => '2026-01-01', 'created_at' => $now]);
$ev = Domain::logMaintenance($uid, ['action_code' => 'BRAKE_BLEED', 'component_id' => $brake, 'bike_id' => null, 'performed_on' => '2026-04-02', 'outcome' => null,
    'measurement_value' => null, 'consumable_id' => $oil, 'consumable_qty' => 20, 'cost_cents' => null, 'shop' => null, 'notes' => null,
    'symptom' => 'spongy lever', 'work_done' => 'lever bleed']);
$b = Workshop::brakeOverview($uid, $bike);
check(count($b) === 1 && $b[0]['last_bleed']['symptom'] === 'spongy lever' && $b[0]['last_bleed']['work_done'] === 'lever bleed', 'brake overview shows the last bleed with symptom and work done');
check($b[0]['fluid'] !== null && $b[0]['position'] === Catalog::slotName('REAR_BRAKE'), 'brake overview shows the fluid reminder and position');
check(Workshop::brakeOverview($uid, $bike2) === [], 'filtered by bike');
check(Inventory::stockLevel($uid, $oil) == 80.0, 'oil used');
Domain::voidMaintenance($uid, $ev, 'wrong brake');
check(Workshop::brakeOverview($uid, $bike)[0]['last_bleed'] === null && Inventory::stockLevel($uid, $oil) == 100.0, 'marked wrong: gone from the overview, oil back');
Domain::restoreMaintenance($uid, $ev);
check(Workshop::brakeOverview($uid, $bike)[0]['last_bleed']['id'] == $ev && Inventory::stockLevel($uid, $oil) == 80.0, 'restored with its oil');
check(Db::value('SELECT void_reason FROM maintenance_events WHERE id = ?', [$ev]) === null, 'restore clears the reason');
Db::run("UPDATE maintenance_events SET voided_at = ?, void_reason = 'undone' WHERE id = ?", [$now, $ev]);
check_throws(fn() => Domain::restoreMaintenance($uid, $ev), 'an entry taken back by an undo cannot be restored', 'Undo');

// ------------------------------------------------------------------ charge history
$pedals = $part('POWER_METER_PEDALS', 'Assioma');
Domain::install($uid, $pedals, $bike2, null, 'PEDALS', '2026-05-01');
check(Workshop::chargeHistory($uid, Domain::component($uid, $chainA)) === null, 'a chain has no charge history');
$ch = Workshop::chargeHistory($uid, Domain::component($uid, $pedals));
check($ch !== null && $ch['charges'] === [] && $ch['average'] === null, 'pedals: empty history before the first charge');
$charge = fn(string $d) => Domain::logMaintenance($uid, ['action_code' => 'POWER_CHARGE', 'component_id' => $pedals, 'bike_id' => null, 'performed_on' => $d,
    'outcome' => null, 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => null]);
$charge('2026-05-01');
$ride('2026-05-02', 50, $bike2, 7200);
$ride('2026-05-05', 30, $bike2, 3600);
$charge('2026-05-11');
$ride('2026-05-11', 20, $bike2, 1800);
$ride('2026-05-12', 70, $bike2, 9000);
$charge('2026-05-31');
$ride('2026-06-01', 10, $bike2, 1800);
$ch = Workshop::chargeHistory($uid, Domain::component($uid, $pedals));
check(count($ch['charges']) === 3 && $ch['charges'][2]['charged_on'] === '2026-05-01', 'three charges, newest first');
check($ch['charges'][2]['km'] == 80.0 && $ch['charges'][2]['hours'] == 3.0 && $ch['charges'][2]['rides'] === 2 && $ch['charges'][2]['days'] === 10, 'first gap: 80 km, 3 h, 2 rides, 10 days');
check($ch['charges'][1]['km'] == 90.0 && $ch['charges'][1]['rides'] === 2 && $ch['charges'][1]['days'] === 20, 'a ride on the charge day counts after that charge');
check($ch['since_last']['km'] == 10.0 && $ch['since_last']['until'] === null, 'since the last charge: 10 km');
check($ch['average'] == ['km' => 85.0, 'hours' => 3.0, 'days' => 15, 'charges' => 2], 'average between charges');

// ------------------------------------------------------------------ backup carries the fits and symptoms
$doc = json_decode(UserBackups::encode(UserBackups::export($uid)), true);
check(count($doc['product_bike_fit']) === 1 && in_array('spongy lever', array_column($doc['maintenance_events'], 'symptom'), true), 'export has fits and symptoms');

// ------------------------------------------------------------------ pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'workshop@example.test', 'password' => 'workshop-tester-pw']);
foreach (["r=part_replace&id=$chainA", "r=brakes", "r=brakes&bike=$bike", "r=part&id=$pedals", "r=product&id=$pChain", "r=group_wheels&bike=$bike2", "r=bike&id=$bike2",
    "r=log&part=$brake&action=BRAKE_BLEED", "r=part&id=$brake"] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->get("r=part&id=$pedals");
check(str_contains($w->body, 'Since the last charge') && str_contains($w->body, 'On average between charges'), 'part page shows the charge history');
$w->get("r=bike&id=$bike2");
check(str_contains($w->body, 'Put them into a wheelset'), 'bike page offers to group loose wheels');
$w->post("r=part_replace&id=$chainA", ['source' => 'same', 'on' => '2026-06-02', 'outcome' => 'STORED', 'carry' => [$link]]);
$newId = (int)Db::value('SELECT component_id FROM installations WHERE bike_id = ? AND slot = ? AND removed_on IS NULL AND voided_at IS NULL', [$bike, 'CHAIN']);
check($newId !== $chainA && $on($link) === ['p' . $newId, 'QUICK_LINK'], 'replace from the page, link carried');
$w->post("r=group_wheels&bike=$bike2", ['on' => '2026-06-02', 'label' => 'Cube wheels']);
check(Workshop::looseWheels($uid, $bike2) === [], 'group wheels from the page');
$w->post("r=product&id=$pChain", ['do' => 'fit', 'bike_id' => $bike2, 'verified' => '0', 'note' => 'probably']);
check(Workshop::fitFor($uid, $pChain, $bike2) === 'UNVERIFIED', 'fit saved from the product page');
$w->post('r=log', ['target' => 'c:' . $brake, 'action_code' => 'BRAKE_BLEED', 'performed_on' => '2026-06-03', 'symptom' => 'soft', 'work_done' => 'full bleed']);
$last = Db::one('SELECT * FROM maintenance_events WHERE component_id = ? ORDER BY id DESC LIMIT 1', [$brake]);
check($last['symptom'] === 'soft' && $last['work_done'] === 'full bleed', 'symptom and work done saved from the form');
$w->post('r=log', ['target' => 'c:' . $pedals, 'action_code' => 'POWER_CHARGE', 'performed_on' => '2026-06-03', 'symptom' => 'x']);
check(Db::value('SELECT symptom FROM maintenance_events WHERE component_id = ? ORDER BY id DESC LIMIT 1', [$pedals]) === null, 'no symptom stored for an action without one');
$w->post("r=event_void&id={$last['id']}", ['reason' => 'test']);
$w->post("r=event_restore&id={$last['id']}", []);
check(Db::value('SELECT voided_at FROM maintenance_events WHERE id = ?', [$last['id']]) === null, 'restore from the page');
$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->post("r=event_restore&id={$last['id']}", []);
check($o->status === 404, 'another user cannot restore my entry');
$o->get("r=part_replace&id=$chainB");
check($o->status === 404, 'another user cannot open my replace form');
$o->post("r=product&id=$pChain", ['do' => 'fit', 'bike_id' => $bike, 'verified' => '1']);
check($o->status === 404, 'another user cannot set my fits');
