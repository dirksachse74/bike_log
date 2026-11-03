<?php
declare(strict_types=1);

// Round 3a: chain rotation, the wax cycle (liquid-wax window, hot wax after a top-up, wet rides), quick link
// per chain (PARENT_COUNT), and the migration that turned the old liquid-wax interval into a window.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'chains@example.test', 'display_name' => 'Chains', 'password_hash' => Auth::hash('chain-gang-secret'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$_SESSION = [];
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Roadie', 'shifting' => 'ELECTRONIC', 'created_at' => $now, 'updated_at' => $now]);
$ride = fn(string $date, float $km, ?string $cond = null) => Db::insert('rides', ['user_id' => $uid, 'bike_id' => $bike, 'ride_date' => $date,
    'distance_km' => $km, 'duration_s' => 3600, 'kind' => 'OUTDOOR', 'conditions' => $cond, 'created_at' => $now, 'updated_at' => $now]);
$chain = fn(string $label, string $mark) => Inventory::createComponent($uid, ['component_type' => 'CHAIN', 'label' => $label, 'mark' => $mark, 'prior_usage' => 'NEW']);
$log = fn(int $cid, string $action, string $on) => Domain::logMaintenance($uid, ['action_code' => $action, 'component_id' => $cid, 'bike_id' => null,
    'performed_on' => $on, 'outcome' => null, 'measurement_value' => null, 'consumable_id' => null, 'consumable_qty' => null, 'cost_cents' => null, 'shop' => null, 'notes' => null]);
$rem = function (int $cid, string $code) use ($uid) {
    foreach (Reminders::forUser($uid, null, $cid) as $r) {
        if (($r['rule']['rule_code'] ?? '') === $code) {
            return $r;
        }
    }
    return null;
};

$rules = Db::all("SELECT * FROM service_rules WHERE user_id = ? AND rule_code IN ('CHAIN_LIQUID_WAX','QUICK_LINK_CHAINS','CHAIN_HOT_WAX')", [$uid]);
$byCode = array_column($rules, null, 'rule_code');
check($byCode['CHAIN_LIQUID_WAX']['trigger_kind'] === 'CYCLE_WINDOW' && (float)$byCode['CHAIN_LIQUID_WAX']['window_min_km'] === 250.0, 'liquid wax is a window rule');
check($byCode['QUICK_LINK_CHAINS']['trigger_kind'] === 'PARENT_COUNT' && (int)$byCode['QUICK_LINK_CHAINS']['interval_count'] === 2, 'quick link rule is seeded');
check((float)$byCode['CHAIN_HOT_WAX']['after_top_up_km'] === 200.0, 'hot wax follows a top-up after 200 km');

$a = $chain('Chain', 'A');
$b = $chain('Chain', 'B');
Domain::install($uid, $a, $bike, null, 'CHAIN', '2026-04-01');
$log($a, 'WAX_HOT', '2026-04-01');
Chains::add($uid, $bike, "c:$b", '2026-04-01');
$log($b, 'WAX_HOT', '2026-04-01');
$rot = Chains::rotation($uid, $bike);
check($rot['on']['id'] === $a && count($rot['ready']) === 1 && $rot['ready'][0]['id'] === $b, 'rotation: A on, B waxed and ready');

// window: 240 km → soon, 260 → open (due)
$ride('2026-04-02', 240.0);
check($rem($a, 'CHAIN_LIQUID_WAX')['status'] === 'SOON', 'liquid wax: window opens soon');
$ride('2026-04-03', 20.0);
$r = $rem($a, 'CHAIN_LIQUID_WAX');
check($r['status'] === 'OVERDUE' && str_contains($r['text'], 'window is open'), 'liquid wax: window open');
// top-up at 260 km: hot wax now due at 460 instead of 500
$log($a, 'WAX_LIQUID', '2026-04-04');
check($rem($a, 'CHAIN_LIQUID_WAX')['status'] === 'OK', 'top-up done for this cycle');
$h = $rem($a, 'CHAIN_HOT_WAX');
check(abs($h['due_km'] - 460.0) < 0.01 && str_contains($h['text'], 'top-up'), 'hot wax due 200 km after the top-up');

// wet ride: asks for a top-up at once (and not a hot wax)
$ride('2026-04-05', 30.0, 'WET');
$r = $rem($a, 'CHAIN_LIQUID_WAX');
check($r['status'] === 'OVERDUE' && str_contains($r['text'], 'wet ride'), 'wet ride asks for a top-up');
check(!str_contains($rem($a, 'CHAIN_HOT_WAX')['text'], 'wet ride'), 'wet ride does not push the hot wax');
$log($a, 'WAX_LIQUID', '2026-04-05');
check($rem($a, 'CHAIN_LIQUID_WAX')['status'] === 'OK', 'top-up after the wet ride (that day) clears it');

// hot wax prompt: A at 470 km → swap to B
$ride('2026-04-06', 180.0);
$rot = Chains::rotation($uid, $bike);
check($rot['prompt'] && $rot['prompt']['kind'] === 'SWAP' && $rot['prompt']['to'] === $b, 'prompt: swap to the ready chain');
Chains::swap($uid, $bike, $b, '2026-04-07');
$rot = Chains::rotation($uid, $bike);
check($rot['on']['id'] === $b && in_array($a, $rot['dirty'], true), 'after the swap B is on, A waits for wax');
check(Domain::component($uid, $a)['disposition'] === 'STORED' && Domain::component($uid, $a)['status'] === 'ACTIVE', 'A is stored, not retired');
$ride('2026-04-07', 50.0);
check(abs(Domain::totals($uid, Domain::component($uid, $b))['total_km'] - 50.0) < 0.01, 'swap-day ride counts for B');
Chains::wax($uid, $bike, [$a], '2026-04-08');
$rows = array_column(Chains::rotation($uid, $bike)['chains'], 'state', 'id');
check($rows[$a] === Chains::READY, 'waxed A is ready again');
$apps = Chains::waxApplications($uid, Domain::component($uid, $a));
check(count($apps) === 4 && $apps[0]['active'] && $apps[1]['type'] === 'Liquid wax top-up' && abs($apps[2]['at_km'] - 260.0) < 0.01, 'wax table: one row per application, top-up at 260 km');
check(count(Chains::timeline($uid, $bike, [$a, $b])) >= 5, 'timeline has stints and waxes');
check_throws(fn() => Chains::swap($uid, $bike, $b, '2026-04-09'), 'cannot swap to the chain that is on', 'already');
check_throws(fn() => Chains::wax($uid, $bike, [], '2026-04-09'), 'wax needs ticked chains', 'Tick');

// a stock chain joins the rotation
$line = Db::insert('consumables', ['user_id' => $uid, 'kind' => 'OTHER', 'tracking_mode' => 'COUNTED', 'component_type' => 'CHAIN', 'name' => 'KMC X12',
    'unit' => 'chain', 'track_stock' => 1, 'created_at' => $now]);
Db::insert('consumable_txns', ['user_id' => $uid, 'consumable_id' => $line, 'kind' => 'BUY', 'qty' => 1, 'happened_on' => '2026-04-01', 'created_at' => $now]);
check(isset(Chains::candidates($uid, $bike)["s:$line"]), 'chain stock is offered');
$c = Chains::add($uid, $bike, "s:$line", '2026-04-09');
check(count(Chains::rotation($uid, $bike)['chains']) === 3 && Inventory::stockLevel($uid, $line) == 0.0, 'stock chain joined, stock went down');

// quick link: limit 2 chains
$ql = Inventory::createComponent($uid, ['component_type' => 'QUICK_LINK', 'label' => 'Connex', 'prior_usage' => 'NEW']);
Domain::install($uid, $ql, null, $b, 'QUICK_LINK', '2026-04-07');
check($rem($ql, 'QUICK_LINK_CHAINS')['status'] === 'OK', 'quick link on 1 chain: ok');
Domain::install($uid, $ql, null, $a, 'QUICK_LINK', '2026-04-08');
Chains::swap($uid, $bike, $a, '2026-04-10');
$r = $rem($ql, 'QUICK_LINK_CHAINS');
check($r['status'] === 'SOON' && str_contains($r['text'], '2 chains'), 'quick link on its 2nd chain: replace at the next change');

// once-after-install with a window: pads bedding taken as done after the window
$pads = Inventory::createComponent($uid, ['component_type' => 'BRAKE_PADS', 'label' => 'Pads', 'prior_usage' => 'NEW']);
Domain::install($uid, $pads, $bike, null, 'REAR_PADS', '2026-04-10');
$bed = array_values(array_filter(Reminders::forUser($uid, null, $pads), fn($x) => ($x['rule']['trigger_kind'] ?? '') === 'ONCE_AFTER_INSTALL'));
check(!$bed || $bed[0]['status'] === 'OVERDUE', 'bed in new pads is asked for');

// lube rule + wet ride (a lubed chain without the top-up rule)
$lubed = $chain('Lubed', 'L');
$bike2 = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Winter', 'shifting' => 'MECHANICAL', 'created_at' => $now, 'updated_at' => $now]);
Domain::install($uid, $lubed, $bike2, null, 'CHAIN', '2026-04-01');
$lubeRule = Db::one("SELECT * FROM service_rules WHERE user_id = ? AND component_type = 'CHAIN' AND action_code = 'LUBE'", [$uid]);
if ($lubeRule) {
    $log($lubed, 'LUBE', '2026-04-01');
    Db::insert('rides', ['user_id' => $uid, 'bike_id' => $bike2, 'ride_date' => '2026-04-02', 'distance_km' => 10, 'kind' => 'OUTDOOR', 'conditions' => 'WET', 'created_at' => $now, 'updated_at' => $now]);
    check($rem($lubed, $lubeRule['rule_code'])['status'] === 'OVERDUE', 'lube after a wet ride');
}

// pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'chains@example.test', 'password' => 'chain-gang-secret']);
foreach (["r=chains&bike=$bike", 'r=chains', "r=part&id=$a", "r=part&id=$ql", 'r=rules', "r=rule_edit&id={$byCode['CHAIN_LIQUID_WAX']['id']}",
    "r=rule_edit&id={$byCode['QUICK_LINK_CHAINS']['id']}", "r=rule_edit&id={$byCode['CHAIN_HOT_WAX']['id']}", "r=part&id=$pads"] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->get("r=part&id=$a");
check(str_contains($w->body, 'Wax applications') && str_contains($w->body, 'Liquid wax top-up'), 'chain page shows the wax table');
$w->post("r=chain_do&bike=$bike", ['do' => 'wax', 'chains' => [$b], 'on' => '2026-04-11', 'then_install' => '']);
check(Db::value("SELECT COUNT(*) FROM maintenance_events WHERE component_id = ? AND action_code = 'WAX_HOT' AND performed_on = '2026-04-11'", [$b]) == 1, 'hot wax through the web');
$w->post("r=chain_do&bike=$bike", ['do' => 'swap', 'to' => $b, 'on' => '2026-04-12']);
check(Chains::rotation($uid, $bike)['on']['id'] === $b, 'swap through the web');
$w->post("r=rule_edit&id={$byCode['CHAIN_LIQUID_WAX']['id']}", ['window_min_km' => '200', 'window_max_km' => '260', 'warn_km' => '20', 'origin' => 'PERSONAL', 'active' => '1']);
check((float)Db::value('SELECT window_max_km FROM service_rules WHERE id = ?', [$byCode['CHAIN_LIQUID_WAX']['id']]) === 260.0, 'edit the window');
$w->post("r=rule_edit&id={$byCode['QUICK_LINK_CHAINS']['id']}", ['interval_count' => '3', 'origin' => 'PERSONAL', 'active' => '1']);
check((int)Db::value('SELECT interval_count FROM service_rules WHERE id = ?', [$byCode['QUICK_LINK_CHAINS']['id']]) === 3, 'edit the quick link limit');
$w->post("r=rule_edit&part=$a&code=CHAIN_LIQUID_WAX", ['window_min_km' => '150', 'window_max_km' => '200', 'origin' => 'PERSONAL', 'active' => '1']);
check((string)Db::value("SELECT cycle_action_code FROM service_rules WHERE component_id = ? AND rule_code = 'CHAIN_LIQUID_WAX'", [$a]) === 'WAX_HOT', 'part copy keeps the cycle');

$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->get("r=chains&bike=$bike");
check($o->status === 404, 'other user cannot see the rotation');
$o->post("r=chain_do&bike=$bike", ['do' => 'swap', 'to' => $a, 'on' => '2026-04-13']);
check(Chains::rotation($uid, $bike)['on']['id'] === $b, 'other user cannot swap my chains');

// the migration converts the base release's liquid-wax interval into a window
Db::run("UPDATE service_rules SET trigger_kind = 'INTERVAL', interval_km = 300, warn_km = 50, window_min_km = NULL, window_max_km = NULL WHERE user_id = ? AND rule_code = 'CHAIN_LIQUID_WAX' AND component_type = 'CHAIN'", [$uid]);
foreach (preg_split('/;\s*$/m', (string)file_get_contents(__DIR__ . '/../sql/migrations/003_wax_cycle_rotation.sql')) as $stmt) {
    if (preg_match('/^\s*UPDATE service_rules SET trigger_kind = .CYCLE_WINDOW/m', $stmt)) {
        Db::run(preg_replace('/^\s*--.*$/m', '', $stmt));
    }
}
$conv = Db::one("SELECT * FROM service_rules WHERE user_id = ? AND rule_code = 'CHAIN_LIQUID_WAX' AND component_type = 'CHAIN'", [$uid]);
check($conv['trigger_kind'] === 'CYCLE_WINDOW' && (float)$conv['window_min_km'] === 250.0 && (float)$conv['window_max_km'] === 300.0 && $conv['interval_km'] === null, 'migration: old interval becomes the 250–300 km window');
