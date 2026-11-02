<?php
declare(strict_types=1);

// Round 4b: per-user backups, restore (with new ids), fresh start, diagnostics, indoor setup.

$now = now_utc();
$src = (int)Db::value("SELECT id FROM users WHERE email = 'costs@example.test'");       // rich data from test_50
$pu = (int)Db::value("SELECT id FROM users WHERE email = 'products@example.test'");    // products, shops, change log from test_60
check($src > 0 && $pu > 0, 'users from earlier tests exist');

$counts = function (int $uid): array {
    $out = [];
    foreach (array_keys(UserBackups::TABLES) as $t) {
        $out[$t] = (int)Db::value("SELECT COUNT(*) FROM $t WHERE user_id = ?", [$uid]);
    }
    $out['user_settings'] = (int)Db::value('SELECT COUNT(*) FROM user_settings WHERE user_id = ?', [$uid]);
    return $out;
};
/** Every reference of the user's rows points to a row of the same user. */
$dangling = function (int $uid): array {
    $bad = [];
    foreach (UserBackups::TABLES as $t => $refs) {
        foreach ($refs as $col => $target) {
            $n = (int)Db::value("SELECT COUNT(*) FROM $t x WHERE x.user_id = ? AND x.$col IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM $target y WHERE y.id = x.$col AND y.user_id = ?)", [$uid, $uid]);
            if ($n) {
                $bad[] = "$t.$col ($n)";
            }
        }
    }
    return $bad;
};
$newUser = function (string $email) use ($now): int {
    $id = Db::insert('users', ['email' => $email, 'display_name' => 'R', 'password_hash' => Auth::hash('restore-tester-pw'), 'role' => 'USER',
        'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
    Domain::seedUser($id);
    return $id;
};
$bikeCost = fn(int $uid) => array_map(fn($b) => Costs::bike($uid, (int)$b['id'])['running'], Db::all('SELECT id FROM bikes WHERE user_id = ? ORDER BY name', [$uid]));
$partKm = fn(int $uid) => array_map(fn($c) => Domain::totals($uid, $c)['total_km'], Db::all('SELECT * FROM components WHERE user_id = ? ORDER BY label, id', [$uid]));

// ------------------------------------------------------------------ export → restore into another account
$before = $counts($src);
$doc = json_decode(UserBackups::encode(UserBackups::export($src)), true);
check($doc['format'] === 'bikelog-php-export' && $doc['version'] === 2 && count($doc['service_orders']) === $before['service_orders'], 'export has every table');
$copy = $newUser('restored@example.test');
UserBackups::restore($copy, $doc, 'test');
$after = $counts($copy);
unset($before['change_log'], $after['change_log']);
check($after === $before, 'restore into another account: same number of rows in every table');
check($dangling($copy) === [], 'restored references all point to the account\'s own rows');
check($bikeCost($copy) === $bikeCost($src), 'costs per bike are the same after the restore');
check($partKm($copy) === $partKm($src), 'km per part are the same after the restore');
check((int)Db::value('SELECT COUNT(*) FROM user_backups WHERE user_id = ? AND reason = ?', [$copy, 'BEFORE_RESTORE']) === 1, 'a copy was stored before the restore');
check(!array_intersect(array_column(Db::all('SELECT id FROM bikes WHERE user_id = ?', [$copy]), 'id'),
    array_column(Db::all('SELECT id FROM bikes WHERE user_id = ?', [$src]), 'id')), 'restored rows have new ids');

// the products user: products, shop list (with merged names) and the change log come along
$pdoc = UserBackups::export($pu);
$copy2 = $newUser('restored2@example.test');
UserBackups::restore($copy2, json_decode(UserBackups::encode($pdoc), true), 'test');
check($dangling($copy2) === [], 'products user restored without dangling references');
check(PickLists::names($copy2) === PickLists::names($pu), 'shop list restored');
check((int)Db::value('SELECT COUNT(*) FROM pick_list_items WHERE user_id = ? AND merged_into_id IS NOT NULL', [$copy2]) >= 1, 'merged shop names keep their link');
$sp = Db::one("SELECT c.id FROM components c WHERE c.user_id = ? AND c.label = 'Saddle Fizik'", [$copy2]);
check($sp && count(ChangeLog::entries($copy2, null, (int)$sp['id'])) >= 3, 'change log entries follow their part');

// ------------------------------------------------------------------ restore over the same account
$cBefore = $counts($src);
UserBackups::restore($src, $doc, 'test');
$cAfter = $counts($src);
unset($cBefore['change_log'], $cAfter['change_log']);
check($cAfter === $cBefore && $dangling($src) === [], 'restore over the same account replaces, not adds');

// ------------------------------------------------------------------ bad files
check_throws(fn() => UserBackups::parse('{"format":"x"}'), 'other format refused', 'not a Bike Log data file');
check_throws(fn() => UserBackups::parse('{"format":"bikelog-php-export","version":99}'), 'newer version refused', 'newer');
$broken = $doc;
$broken['installations'][0]['component_id'] = 999999;
$keep = $counts($copy);
check_throws(fn() => UserBackups::restore($copy, $broken, 'broken'), 'dangling reference refused', 'not in the file');
check($counts($copy) === $keep, 'a refused file changes nothing');
$broken = $doc;
unset($broken['bikes'][0]['name']);
check_throws(fn() => UserBackups::restore($copy, $broken, 'broken'), 'missing required field refused', 'name is missing');
$old = $doc;
$old['version'] = 1;
unset($old['purchase_bundles'], $old['service_orders'], $old['pick_list_items'], $old['change_log']);
foreach ($old['components'] as &$c) {
    $c['bundle_id'] = null;
}
unset($c);
foreach ($old['maintenance_events'] as &$e) {
    $e['work_session_id'] = $e['work_session_id'];
}
unset($e);
$copy3 = $newUser('restored3@example.test');
UserBackups::restore($copy3, $old, 'v1');
check($counts($copy3)['bikes'] === count($doc['bikes']) && $dangling($copy3) === [], 'a version 1 file (fewer tables) restores');

// ------------------------------------------------------------------ fresh start
$fs = $newUser('fresh@example.test');
$b = Db::insert('bikes', ['user_id' => $fs, 'name' => 'Old bike', 'created_at' => $now, 'updated_at' => $now]);
Db::insert('rides', ['user_id' => $fs, 'bike_id' => $b, 'ride_date' => '2026-05-01', 'distance_km' => 40, 'kind' => 'OUTDOOR', 'created_at' => $now, 'updated_at' => $now]);
UserSettings::set($fs, 'spoke_relace_after', '7');
$rules = (int)Db::value('SELECT COUNT(*) FROM service_rules WHERE user_id = ?', [$fs]);
$bid = UserBackups::freshStart($fs);
$c = $counts($fs);
check($c['bikes'] === 0 && $c['rides'] === 0 && $c['user_settings'] === 0 && $c['service_rules'] === $rules, 'fresh start: data gone, default rules back');
check(UserSettings::get($fs, 'spoke_relace_after') === '3', 'settings back to defaults');
UserBackups::restore($fs, UserBackups::parse(UserBackups::content($fs, $bid)), 'undo');
check((int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ?', [$fs]) === 1 && UserSettings::get($fs, 'spoke_relace_after') === '7', 'the copy from before the fresh start restores it');
for ($i = 0; $i < UserBackups::KEEP + 2; $i++) {
    UserBackups::save($fs, 'MANUAL');
}
check(count(UserBackups::rows($fs)) === UserBackups::KEEP, 'only the newest copies are kept');
check_throws(fn() => UserBackups::content($src, $bid), 'another user\'s copy is not found', 'not found');

// ------------------------------------------------------------------ indoor (direct-drive trainer)
check(in_array('CASSETTE', Catalog::INDOOR_EXCLUDED, true), 'cassette does not wear on a direct-drive trainer');

// ------------------------------------------------------------------ pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'fresh@example.test', 'password' => 'restore-tester-pw']);
foreach (['r=backups', 'r=fresh_start', 'r=diagnostics', 'r=account'] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
$w->post('r=fresh_start', ['current' => 'restore-tester-pw', 'confirm' => 'reset']);
check((int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ?', [$fs]) === 1, 'fresh start needs the word RESET');
$w->post('r=fresh_start', ['current' => 'wrong', 'confirm' => 'RESET']);
check((int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ?', [$fs]) === 1, 'fresh start needs the password');
$w->post('r=fresh_start', ['current' => 'restore-tester-pw', 'confirm' => 'RESET']);
check((int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ?', [$fs]) === 0, 'fresh start from the page');
$w->upload('r=backups', ['do' => 'upload', 'confirm' => 'RESTORE'], ['file' => [['mine.json', UserBackups::encode($doc)]]]);
check(str_contains($w->body, 'Restored:') && (int)Db::value('SELECT COUNT(*) FROM bikes WHERE user_id = ?', [$fs]) === count($doc['bikes']), 'restore from an uploaded file');
$last = UserBackups::rows($fs)[0];
$w->post("r=backups&id={$last['id']}", ['do' => 'download']);
check($w->status === 200 && json_decode($w->body, true)['format'] === 'bikelog-php-export', 'stored copy downloads');
$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->post("r=backups&id={$last['id']}", ['do' => 'download']);
check($o->status === 404, 'other user cannot download my copy');
$o->post("r=backups&id={$last['id']}", ['do' => 'restore', 'confirm' => 'RESTORE']);
check($o->status === 404 && (int)Db::value('SELECT COUNT(*) FROM bikes WHERE user_id = ?', [$fs]) === count($doc['bikes']), 'other user cannot restore my copy');
