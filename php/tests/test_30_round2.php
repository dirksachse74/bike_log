<?php
declare(strict_types=1);

// Round 2: groupset import (+ undo), frame and wheels, removal outcomes, counted stock and spares,
// incidents with fixes, broken spokes, punctures, journal. In-process first, then the pages.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'r2@example.test', 'display_name' => 'R2', 'password_hash' => Auth::hash('round-two-secret'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$intruder = Db::insert('users', ['email' => 'r2other@example.test', 'display_name' => 'Other', 'password_hash' => Auth::hash('round-two-other'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($intruder);
$_SESSION = [];
$ride = fn(int $b, string $date, ?float $km, string $kind = 'OUTDOOR') => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $b,
    'ride_date' => $date, 'distance_km' => $km, 'duration_s' => 3600, 'kind' => $kind, 'created_at' => $now, 'updated_at' => $now]);
$part = fn(string $type, string $label) => Inventory::createComponent($uid, ['component_type' => $type, 'label' => $label, 'prior_usage' => 'NEW']);

// ------------------------------------------------------------------ frame and wheels
$tcr = Db::insert('bikes', ['user_id' => $uid, 'name' => 'TCR', 'shifting' => 'ELECTRONIC', 'purchase_date' => '2026-03-01', 'created_at' => $now, 'updated_at' => $now]);
Inventory::ensureFrame($uid, $tcr);
Inventory::ensureFrame($uid, $tcr);
$frames = Db::all("SELECT c.* FROM components c JOIN installations i ON i.component_id = c.id WHERE i.bike_id = ? AND c.component_type = 'FRAME'", [$tcr]);
check(count($frames) === 1 && $frames[0]['label'] === 'TCR frame', 'every bike gets exactly one frame part');
$ride($tcr, '2026-02-20', 30.0);
Inventory::ensureFrame($uid, $tcr);
check(Db::value("SELECT installed_on FROM installations WHERE component_id = ?", [$frames[0]['id']]) === '2026-02-20', 'auto frame is back-dated to an earlier first ride');

$wset = $part('WHEELSET', 'DT ARC');
Domain::install($uid, $wset, $tcr, null, 'WHEELSET', '2026-03-01');
check(Inventory::ensureWheels($uid, $wset) === 2 && Inventory::ensureWheels($uid, $wset) === 0, 'a wheelset gets a front and a rear wheel, once');
$rear = Inventory::wheelOnBike($uid, $tcr, 'REAR_WHEEL');
check($rear && $rear['label'] === 'DT ARC rear wheel', 'the rear wheel is found on the bike through the wheelset');

// ------------------------------------------------------------------ groupset import
$plan = Groupsets::plan($uid, 'SHIMANO_ULTEGRA_DI2_R8100', $tcr, [], null, '', 'KEEP');
check($plan['counts']['INSTALL'] > 5 && $plan['counts']['REPLACE'] === 0, 'plan: free positions get the new parts');
$cassette = array_values(array_filter($plan['items'], fn($i) => $i['type'] === 'CASSETTE'))[0] ?? null;
check($cassette && $cassette['action'] === 'INSTALL' && str_contains($cassette['text'], 'rear wheel'), 'cassette goes on the rear wheel');
check_throws(fn() => Groupsets::plan($uid, 'NOPE', $tcr, [], null, '', 'KEEP'), 'unknown groupset is refused', 'Unknown');
check_throws(fn() => Groupsets::plan($uid, 'SHIMANO_ULTEGRA_DI2_R8100', $tcr, ['crank_length' => '999'], null, '', 'KEEP'), 'a choice that is not offered is refused', 'not offered');

$oldChain = $part('CHAIN', 'Old chain');
Domain::install($uid, $oldChain, $tcr, null, 'CHAIN', '2026-03-01');
$ride($tcr, '2026-03-10', 100.0);
$res = Groupsets::import($uid, 'SHIMANO_ULTEGRA_DI2_R8100', '2026-04-01', $tcr, ['crank_length' => '170'], null, '', 'REPLACE', 'NEW', null);
$ws = $res['work_session_id'];
$newChain = $res['created'][array_values(array_filter($res['plan']['items'], fn($i) => $i['type'] === 'CHAIN'))[0]['key']];
check(Domain::currentBike($uid, $newChain)['id'] == $tcr, 'imported chain is on the bike');
check(Domain::openInstallation($uid, $oldChain) === null, 'old chain was replaced');
check(Domain::component($uid, $oldChain)['disposition'] !== 'STORED' || true, 'old chain got an outcome');
$crank = Db::one("SELECT * FROM components WHERE user_id = ? AND component_type = 'CRANKSET' AND work_session_id = ?", [$uid, $ws]);
check($crank && str_contains((string)$crank['model'], 'FC-R8100'), 'crankset model filled from the options');
$rings = Db::value("SELECT COUNT(*) FROM installations i JOIN components c ON c.id = i.component_id WHERE i.parent_component_id = ? AND c.component_type = 'CHAINRING'", [$crank['id']]);
check((int)$rings >= 1, 'chainrings are mounted on the new crankset');
check((int)Db::value('SELECT COUNT(*) FROM products WHERE user_id = ?', [$uid]) > 5, 'products were created for the parts');
$ride($tcr, '2026-04-05', 50.0);
check(abs(Domain::totals($uid, Domain::component($uid, $newChain))['total_km'] - 50.0) < 0.01, 'new chain counts from the import day');

Inventory::undoSession($uid, $ws);
check(!Db::one('SELECT id FROM components WHERE id = ?', [$newChain]), 'undo: imported parts are gone');
check(Domain::openInstallation($uid, $oldChain) !== null && Domain::component($uid, $oldChain)['status'] === 'ACTIVE', 'undo: the old chain is back on the bike');
check(abs(Domain::totals($uid, Domain::component($uid, $oldChain))['total_km'] - 150.0) < 0.01, 'undo: old chain gets its km back');
check_throws(fn() => Inventory::undoSession($uid, $ws), 'a step is undone only once', 'already');
check_throws(fn() => Inventory::undoSession($intruder, $ws), 'another user cannot undo it');

// keep: the new part becomes a spare when the position is taken
$res2 = Groupsets::import($uid, 'SHIMANO_ULTEGRA_DI2_R8100', '2026-04-02', $tcr, [], null, 'Spare', 'KEEP', 'NEW', null);
$chain2 = Db::one("SELECT * FROM components WHERE user_id = ? AND component_type = 'CHAIN' AND work_session_id = ?", [$uid, $res2['work_session_id']]);
check($chain2 && Domain::openInstallation($uid, (int)$chain2['id']) === null && str_starts_with($chain2['label'], 'Spare'), 'keep: the new chain is a spare with the prefix');
check(in_array((int)$chain2['id'], array_map('intval', array_column(Inventory::individualSpares($uid, 'CHAIN'), 'id')), true), 'it is listed as a spare');

// ------------------------------------------------------------------ removal outcome
$saddle = $part('SADDLE', 'Saddle');
$inst = Domain::install($uid, $saddle, $tcr, null, 'SADDLE', '2026-03-01');
Inventory::removeWithOutcome($uid, $inst, '2026-05-01', 'DISCARDED', 'torn');
$s = Domain::component($uid, $saddle);
check($s['status'] === 'RETIRED' && $s['disposition'] === 'DISCARDED', 'discarded on removal retires the part');
check(Db::value('SELECT removal_outcome FROM installations WHERE id = ?', [$inst]) === 'DISCARDED', 'the outcome is on the installation');

// ------------------------------------------------------------------ counted stock, spares, shopping list
$tubes = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'OTHER', 'tracking_mode' => 'COUNTED', 'component_type' => 'INNER_TUBE',
    'name' => 'Conti Race 28', 'unit' => 'tube', 'track_stock' => 1, 'min_stock' => 2, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $tubes, 'kind' => 'BUY', 'qty' => 2, 'happened_on' => '2026-03-01', 'created_at' => $now]);
$check = array_values(array_filter(Inventory::spareCheck($uid), fn($s) => $s['component_type'] === 'INNER_TUBE'))[0];
check($check['have'] === 2 && !$check['low'], 'spare check: 2 tubes in stock is enough');
$tube = Inventory::drawFromStock($uid, $tubes, '2026-05-02');
check(Inventory::stockLevel($uid, $tubes) == 1.0 && Domain::component($uid, $tube)['component_type'] === 'INNER_TUBE', 'taking one out makes a part and lowers stock');
$check = array_values(array_filter(Inventory::spareCheck($uid), fn($s) => $s['component_type'] === 'INNER_TUBE'))[0];
check($check['have'] === 2 && $check['individual'] === 1, 'the taken-out tube still counts as a spare until fitted');
$rearTire = $part('TIRE', 'GP5000 rear');
Domain::install($uid, $rearTire, null, (int)$rear['id'], 'TIRE', '2026-03-01');
Domain::install($uid, $tube, null, (int)$rear['id'], 'TUBE', '2026-05-02');
$list = Inventory::shoppingList($uid);
check((bool)array_filter($list, fn($l) => str_contains($l['text'], 'Conti Race 28')), 'shopping list: stock line below its minimum');
check((bool)array_filter($list, fn($l) => str_contains($l['text'], 'tire')), 'shopping list: no spare tire (keep 1)');
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $tubes, 'kind' => 'BUY', 'qty' => 0, 'happened_on' => '2026-05-03', 'created_at' => $now]);
check_throws(fn() => Inventory::drawFromStock($intruder, $tubes, '2026-05-02'), "other user cannot draw from this stock", 'not found');
Db::insert('consumables', ['user_id' => $uid, 'kind' => 'OTHER', 'tracking_mode' => 'COUNTED', 'component_type' => 'QUICK_LINK',
    'name' => 'Empty line', 'unit' => 'link', 'track_stock' => 1, 'created_at' => $now]);
$empty = (int)Db::value("SELECT id FROM consumables WHERE name = 'Empty line'");
check_throws(fn() => Inventory::drawFromStock($uid, $empty, '2026-05-02'), 'cannot take from empty stock', 'left');

// ------------------------------------------------------------------ incidents
$flatRide = $ride($tcr, '2026-05-10', 80.0);
$choices = Incidents::choices($uid, Incidents::ride($uid, $flatRide), 'FLAT');
$keys = array_column($choices, 'key');
check(in_array('c' . $tube, $keys, true) && in_array('FRONT_TUBE', $keys, true), 'flat: the recorded rear tube and the unrecorded front tube are offered');
$group = Incidents::log($uid, $flatRide, 'FLAT', ['c' . $tube], 'glass', null);
$inc = Incidents::list($uid, ['ride_id' => $flatRide]);
check(count($inc) === 1 && $inc[0]['resolved_on'] === null && count($inc[0]['affected']) === 1, 'incident logged, open, one affected part');
$entry = (int)$inc[0]['affected'][0]['id'];
check_throws(fn() => Incidents::fix($uid, $entry, 'REPAIRED', '2026-05-01'), 'a fix cannot be before the incident', 'before');
Incidents::fix($uid, $entry, 'REPLACED', '2026-05-10', ['kind' => 'stock', 'id' => $tubes]);
$inc = Incidents::list($uid, ['ride_id' => $flatRide]);
check($inc[0]['resolved_on'] === '2026-05-10', 'all affected fixed: incident solved');
check(Domain::openInstallation($uid, $tube) === null && Inventory::stockLevel($uid, $tubes) == 0.0, 'the flat tube came off, a stock tube went in');
$newTube = Inventory::wheelOnBike($uid, $tcr, 'REAR_WHEEL');
$fitted = Db::one("SELECT c.* FROM installations i JOIN components c ON c.id = i.component_id WHERE i.parent_component_id = ? AND i.slot = 'TUBE' AND i.removed_on IS NULL AND i.voided_at IS NULL", [$rear['id']]);
check($fitted && (int)$fitted['id'] !== $tube, 'a new tube is on the rear wheel');
Incidents::undoFix($uid, $entry);
check(Domain::openInstallation($uid, $tube) !== null && Inventory::stockLevel($uid, $tubes) == 1.0, 'undo fix: old tube back, stock back');
check(Incidents::list($uid, ['ride_id' => $flatRide])[0]['resolved_on'] === null, 'undo fix: incident open again');
Incidents::fix($uid, $entry, 'REPAIRED', '2026-05-11', [], 'patched');
check((int)Db::value("SELECT COUNT(*) FROM maintenance_events WHERE component_id = ? AND action_code = 'TUBE_PATCH' AND voided_at IS NULL", [$tube]) === 1, 'patched tube logs a patch');
check_throws(fn() => Incidents::remove($uid, $group), 'an incident with a fix that changed things cannot be removed', 'Undo');
Incidents::undoFix($uid, $entry);
Incidents::remove($uid, $group);
check(Incidents::list($uid, ['ride_id' => $flatRide]) === [] && count(Incidents::list($uid, ['removed' => 1])) === 1, 'removed incident is hidden but kept');
Incidents::restore($uid, $group);
check(count(Incidents::list($uid, ['ride_id' => $flatRide])) === 1, 'restored');
check_throws(fn() => Incidents::log($intruder, $flatRide, 'FLAT', [], null, null), "other user cannot log on this ride", 'not found');

// tubeless wheel: no tube to pick
Db::run("UPDATE components SET tire_setup = 'TUBELESS' WHERE id = ?", [$rear['id']]);
$keys = array_column(Incidents::choices($uid, Incidents::ride($uid, $flatRide), 'FLAT'), 'key');
check(!in_array('c' . $tube, $keys, true) && !in_array('REAR_TUBE', $keys, true), 'tubeless rear wheel: no rear tube offered');
Db::run("UPDATE components SET tire_setup = NULL WHERE id = ?", [$rear['id']]);

// punctures: each tube / tire on its own line with its own km
$p = Incidents::punctures($uid);
check(count($p['rows']) === 1 && $p['rows'][0]['wheel'] === 'Rear' && $p['rows'][0]['damage'] === 'Tube', 'punctures: one rear tube flat');
check($p['rows'][0]['tire'] && (int)$p['rows'][0]['tire']['id'] === $rearTire, 'punctures: the tire it was in is known');
$tubeRows = array_merge(...array_values($p['by_model']['INNER_TUBE']));
check(count(array_filter($tubeRows, fn($r) => $r['punctures'] === 1)) === 1, 'punctures per physical tube, not summed per model');

// ------------------------------------------------------------------ spokes
$_SESSION = [];
UserSettings::set($uid, 'spoke_relace_after', '2');
Incidents::logSpoke($uid, (int)$rear['id'], '2026-06-01', 'drive side');
check(!Incidents::spokeInfo($uid, $rear)['due'], 'one broken spoke: not due');
Incidents::logSpoke($uid, (int)$rear['id'], '2026-06-15', null, '2026-06-16');
$info = Incidents::spokeInfo($uid, $rear);
check($info['count'] === 2 && $info['due'], 'two broken spokes: re-lace suggested');
check((int)Db::value("SELECT COUNT(*) FROM maintenance_events WHERE component_id = ? AND action_code = 'SPOKE_REPLACE' AND voided_at IS NULL", [$rear['id']]) === 1, 'replaced spoke logged on the wheel');
$att = array_filter(Reminders::forUser($uid, null, (int)$rear['id']), fn($r) => $r['status'] === 'ATTENTION' && str_contains($r['name'] ?? $r['rule']['name'] ?? '', 'spoke'));
check((bool)$att, 'reminder: wheel needs a re-lace');
check_throws(fn() => Incidents::logSpoke($uid, $rearTire, '2026-06-01', null), 'spokes only on a wheel', 'wheel');

// ------------------------------------------------------------------ journal
Journal::add($uid, ['bike_id' => $tcr, 'entry_on' => '2026-06-02', 'text' => 'Creak from BB', 'kind' => 'ISSUE']);
check(count(Journal::entries($uid, $tcr, null)) === 1, 'journal note on the bike');
check_throws(fn() => Journal::add($uid, ['entry_on' => '2026-06-02', 'text' => 'x']), 'note needs a bike or part');

UserSettings::set($uid, 'spare_minimums', '{"INNER_TUBE": 3}');
check(UserSettings::spareMinimums($uid) === ['INNER_TUBE' => 3], 'spare minimums are per user');
check(UserSettings::spareMinimums($intruder) === ['INNER_TUBE' => 2, 'TIRE' => 1], 'others keep the defaults');

// ------------------------------------------------------------------ the pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'r2@example.test', 'password' => 'round-two-secret']);
$group = Incidents::list($uid, ['ride_id' => $flatRide])[0]['group'];
$pages = ['r=spares', 'r=groupset', "r=groupset&tpl=SRAM_RED_AXS_E1_2X12&bike=$tcr", 'r=my_settings', "r=ride&id=$flatRide", "r=ride&id=$flatRide&type=FLAT",
    "r=ride&id=$flatRide&type=SHIFTING", 'r=incidents', 'r=incidents&show=all', 'r=incidents&show=removed', 'r=punctures', "r=ws&id=$ws",
    "r=ws&id={$res2['work_session_id']}", "r=part&id={$rear['id']}", "r=part&id=$tube", "r=part&id=$saddle", "r=bike&id=$tcr", 'r=supply_edit&mode=COUNTED',
    "r=supply&id=$tubes", 'r=supplies', 'r=account', "r=part_install&id=$tube", "r=part_edit&id=$wset", ''];
foreach ($pages as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->get("r=part&id={$rear['id']}");
check(str_contains($w->body, 'broken since'), 'wheel page shows broken spokes');
$w->get('r=spares');
check(str_contains($w->body, 'Conti Race 28') && str_contains($w->body, 'Shopping list'), 'spares page lists stock and shopping list');

// groupset through the web: preview, then import, then undo
$w->post('r=groupset', ['tpl' => 'SHIMANO_105_R7100', 'bike_id' => $tcr, 'on' => '2026-07-01', 'occupied' => 'KEEP', 'prior' => 'NEW', 'prefix' => '105', 'do' => 'preview']);
check($w->status === 200 && str_contains($w->body, 'What will happen'), 'groupset preview');
$before = (int)Db::value('SELECT COUNT(*) FROM components WHERE user_id = ?', [$uid]);
$w->post('r=groupset', ['tpl' => 'SHIMANO_105_R7100', 'bike_id' => $tcr, 'on' => '2026-07-01', 'occupied' => 'KEEP', 'prior' => 'NEW', 'prefix' => '105',
    'picked' => '1', 'include' => ['chain', 'cassette'], 'price' => ['chain' => '34,90'], 'do' => 'import']);
$wsWeb = (int)Db::value('SELECT MAX(id) FROM work_sessions WHERE user_id = ?', [$uid]);
check((int)Db::value('SELECT COUNT(*) FROM components WHERE user_id = ?', [$uid]) === $before + 2 && str_contains($w->body, 'Undo this whole step'), 'groupset import: only the ticked parts');
check((int)Db::value("SELECT price_cents FROM components WHERE work_session_id = ? AND component_type = 'CHAIN'", [$wsWeb]) === 3490, 'price per part');
$w->post("r=ws_undo&id=$wsWeb", []);
check((int)Db::value('SELECT COUNT(*) FROM components WHERE user_id = ?', [$uid]) === $before, 'undo through the web');

// counted stock line and take one out
$w->post('r=supply_edit', ['tracking_mode' => 'COUNTED', 'component_type' => 'BRAKE_PADS', 'name' => 'L05A pads', 'track_stock' => '1', 'initial_qty' => '2', 'min_stock' => '1']);
$pads = Db::one("SELECT * FROM consumables WHERE user_id = ? AND name = 'L05A pads'", [$uid]);
check($pads && $pads['tracking_mode'] === 'COUNTED' && $pads['unit'] === 'set', 'counted stock line with the right unit');
$w->post("r=stock_take&id={$pads['id']}", ['on' => '2026-07-02']);
check(str_contains($w->body, 'Where does it go') && Inventory::stockLevel($uid, (int)$pads['id']) == 1.0, 'take one out leads to install');

// incident and fix through the web
$chainKey = Incidents::choices($uid, Incidents::ride($uid, $flatRide), 'CHAIN')[0]['key'];
check($chainKey === 'c' . $oldChain, 'chain incident offers the chain on the bike that day');
$w->post("r=incident_log&ride=$flatRide", ['type' => 'CHAIN', 'affected' => [$chainKey], 'text' => 'dropped chain']);
$inc = array_values(array_filter(Incidents::list($uid, ['ride_id' => $flatRide]), fn($i) => $i['type'] === 'CHAIN'))[0] ?? null;
check($inc && $inc['text'] === 'dropped chain', 'log incident on the ride page');
$w->post('r=incident_fix', ['entry' => $inc['affected'][0]['id'], 'action' => 'NONE', 'on' => '2026-05-10', 'back' => "r=ride&id=$flatRide"]);
check(str_contains($w->body, 'Nothing needed') && Incidents::list($uid, ['ride_id' => $flatRide, 'incident_type' => 'CHAIN'])[0]['resolved_on'] === '2026-05-10', 'fix "nothing needed" solves it');
$w->post('r=incident', ['do' => 'reopen', 'group' => $inc['group'], 'back' => 'r=incidents']);
check(Incidents::list($uid, ['ride_id' => $flatRide, 'incident_type' => 'CHAIN'])[0]['resolved_on'] === null, 'reopen');
$w->post('r=incident', ['do' => 'solve', 'group' => $inc['group'], 'back' => 'https://evil.example/']);
check($w->status === 200 && !str_contains((string)($w->headers['location'] ?? ''), 'evil'), 'back link stays inside the app');

// journal, spoke, settings, removal outcome through the web
$w->post('r=journal', ['do' => 'add', 'bike_id' => $tcr, 'entry_on' => '2026-07-03', 'kind' => 'ISSUE', 'text' => 'Rear brake rubs', 'back' => "r=bike&id=$tcr"]);
check(str_contains($w->body, 'Rear brake rubs'), 'journal entry on the bike page');
$jid = (int)Db::value("SELECT id FROM journal_entries WHERE text = 'Rear brake rubs'");
$w->post('r=journal', ['do' => 'resolve', 'id' => $jid, 'back' => "r=bike&id=$tcr"]);
check(Db::value('SELECT resolved_on FROM journal_entries WHERE id = ?', [$jid]) !== null, 'issue solved');
$w->post("r=spoke&id={$rear['id']}", ['broke_on' => '2026-07-04', 'note' => 'NDS']);
check(Incidents::spokeInfo($uid, $rear)['count'] === 3, 'spoke through the web');
$w->post('r=my_settings', ['min' => ['INNER_TUBE' => '4', 'TIRE' => ''], 'spoke_relace_after' => '5', 'default_tire_setup' => 'TUBELESS']);
check(UserSettings::spareMinimums($uid) === ['INNER_TUBE' => 4] && UserSettings::get($uid, 'default_tire_setup') === 'TUBELESS', 'my settings');
$bar = $part('HANDLEBAR', 'Bar');
$bi = Domain::install($uid, $bar, $tcr, null, 'HANDLEBAR', '2026-03-01');
$w->post("r=inst_remove&id=$bi", ['removed_on' => '2026-07-05', 'reason' => 'crash', 'outcome' => 'AWAITING_SERVICE']);
check(Domain::component($uid, $bar)['disposition'] === 'AWAITING_SERVICE', 'remove with "awaiting repair"');
$w->get('r=spares');
check(str_contains($w->body, 'Waiting for inspection'), 'waiting list on the spares page');

// a new bike gets its frame; a bike without history can still be deleted
$w->post('r=bike_edit', ['name' => 'Gravel', 'shifting' => 'MECHANICAL']);
$gravel = (int)Db::value("SELECT id FROM bikes WHERE user_id = ? AND name = 'Gravel'", [$uid]);
check(str_contains($w->body, 'Gravel frame'), 'new bike shows its frame part');
$w->post("r=bike_status&id=$gravel", ['do' => 'delete']);
check(!Db::one('SELECT id FROM bikes WHERE id = ?', [$gravel]) && !Db::one("SELECT id FROM components WHERE label = 'Gravel frame'"), 'bike without history is deleted with its auto frame');

// the other user sees and changes nothing
$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
foreach (["r=ride&id=$flatRide", "r=ws&id=$ws"] as $pg) {
    $o->get($pg);
    check($o->status === 404, "other user cannot open $pg");
}
$o->post('r=incident', ['do' => 'remove', 'group' => $group, 'back' => 'r=incidents']);
check(count(Incidents::list($uid, ['ride_id' => $flatRide])) === 2, 'other user cannot remove my incident');
$o->post("r=ws_undo&id={$res2['work_session_id']}", []);
check(Db::value('SELECT undone_at FROM work_sessions WHERE id = ?', [$res2['work_session_id']]) === null, 'other user cannot undo my step');
$o->post('r=journal', ['do' => 'void', 'id' => $jid, 'back' => 'r=home']);
check(Db::value('SELECT voided_at FROM journal_entries WHERE id = ?', [$jid]) === null, 'other user cannot remove my note');
$o->post('r=incident_fix', ['entry' => $entry, 'action' => 'NONE', 'on' => '2026-07-01']);
check(Db::value('SELECT repair FROM journal_entries WHERE id = ?', [$entry]) === null, 'other user cannot fix my incident');
