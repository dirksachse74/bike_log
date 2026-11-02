<?php
declare(strict_types=1);

// Round 4a: products and the JSON product import, the shop list, the change log.

$now = now_utc();
$uid = Db::insert('users', ['email' => 'products@example.test', 'display_name' => 'Products', 'password_hash' => Auth::hash('product-person-pw'),
    'role' => 'USER', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$_SESSION = [];

// ------------------------------------------------------------------ validation
$j = fn(string $s) => Products::parse($s);
$v = Products::validate($j('{"component_type":"NOPE","maker":"","model":"X","specs":{"speeds":"11,5"},"foo":1}'));
check(!$v['products'] && count($v['errors']) >= 3, 'bad file: errors for type, maker and unknown field');
check((bool)array_filter($v['errors'], fn($e) => str_starts_with($e, 'file.component_type')), 'errors name their place (file.component_type)');
$v = Products::validate($j('{"format":"bikelog.products.v1","products":[{"component_type":"CHAIN","maker":"Shimano","model":"CN-M8100","specs":{"speeds":"12","links":11.5}},
    {"component_type":"CHAIN","maker":"shimano","model":"cn-m8100"}]}'));
check(in_array('products[0].specs.links: expected a whole number, got 11.5', $v['errors'], true), 'whole-number check with path');
check((bool)array_filter($v['warnings'], fn($w) => str_contains($w, 'read as a number')), 'text number read with a warning');
$v = Products::validate($j('[{"component_type":"CHAIN","maker":"Shimano","model":"CN-M8100"},{"component_type":"CHAIN","maker":"shimano","model":"cn-m8100 "}]'));
check(($v['errors'][0] ?? '') === 'products[1]: same product as products[0] (shimano cn-m8100 )', 'same product twice in one file is an error');
check_throws(fn() => Products::parse('{"a":'), 'broken JSON is rejected', 'Not valid JSON');
// desktop app files import unchanged
foreach (['tire', 'chain', 'cassette', 'brake_rotor'] as $t) {
    $f = dirname(__DIR__, 2) . "/docs/product-templates/$t.example.json";
    if (is_file($f)) {
        $v = Products::validate(Products::parse((string)file_get_contents($f)));
        check(!$v['errors'] && count($v['products']) === 1, "desktop template $t.example.json is valid here");
    }
}
foreach (['CHAIN', 'TIRE', 'OTHER'] as $t) {
    check(!Products::validate(json_decode(json_encode(Products::example($t)), false))['errors'], "own example for $t validates");
}

// ------------------------------------------------------------------ import
$file = '{"format":"bikelog.product.v1","component_type":"CHAIN","maker":"Shimano","model":"CN-M8100","list_price":39.9,
  "specs":{"speeds":12,"links":126,"stack":"x"},"source":{"url":"https://example.com/c","retrieved_at":"2026-10-25","tool":"t 1"},
  "items":[{"label":"Spare chain 1","price":35,"purchase_date":"2026-10-01","storage_location":"Drawer"}]}';
$r = Products::import($uid, $j($file), true);
check($r['ok'] && $r['counts']['CREATED'] === 1 && $r['counts']['ITEMS_CREATED'] === 1, 'dry run reports what would happen');
check((int)Db::value('SELECT COUNT(*) FROM products WHERE user_id = ?', [$uid]) === 0, 'dry run writes nothing');
$r = Products::import($uid, $j($file));
$pid = $r['products'][0]['product_id'];
$p = Products::get($uid, $pid);
check($r['ok'] && (int)$p['list_price_cents'] === 3990 && json_decode($p['specs_json'], true)['links'] === 126, 'product created with price and specs');
check(str_contains($p['spec_version'], 'unverified') && $p['spec_source'] === 'https://example.com/c', 'source and unverified mark kept');
$spare = Db::one('SELECT * FROM components WHERE user_id = ? AND label = ?', [$uid, 'Spare chain 1']);
check($spare && (int)$spare['product_id'] === $pid && (int)$spare['price_cents'] === 3500 && $spare['storage_location'] === 'Drawer', 'item added as a spare of the product');
$r = Products::import($uid, $j($file));
check($r['counts']['UNCHANGED'] === 1 && $r['counts']['ITEMS_EXISTING'] === 1, 'same file again changes nothing');
Db::run('UPDATE products SET specs_json = ? WHERE id = ?', [json_encode(['speeds' => 12, 'links' => 126, 'stack' => 'x', 'my_note' => 'kept']), $pid]);
$r = Products::import($uid, $j(str_replace('"links":126', '"links":116', $file)));
$specs = json_decode(Products::get($uid, $pid)['specs_json'], true);
check($r['counts']['UPDATED'] === 1 && $r['products'][0]['changed'] === ['links'] && $specs['links'] === 116 && $specs['my_note'] === 'kept',
    'changed file updates the product; keys only in the app are kept');
// all or nothing: an item label used by another product's part stops the whole file
$other = Db::insert('products', ['user_id' => $uid, 'component_type' => 'CHAIN', 'maker' => 'KMC', 'model' => 'X12', 'created_at' => $now]);
Db::run('UPDATE components SET product_id = ? WHERE id = ?', [$other, $spare['id']]);
check_throws(fn() => Products::import($uid, $j('{"format":"bikelog.products.v1","products":[{"component_type":"TIRE","maker":"Conti","model":"GP5000"},
    {"component_type":"CHAIN","maker":"Shimano","model":"CN-M8100","items":[{"label":"Spare chain 1"}]}]}')), 'item label of another product', 'another product');
check(!Inventory::findProduct($uid, 'TIRE', 'Conti', 'GP5000'), 'nothing from the failed file was written');

// typed specs
$s = Products::parseSpecLines('CHAIN', "speeds: 12\nlinks: 116\ncolour finish: silver");
check($s === ['speeds' => 12, 'links' => 116, 'colour_finish' => 'silver'], 'spec lines: known keys typed, others kept as text');
check_throws(fn() => Products::parseSpecLines('CHAIN', 'speeds: many'), 'bad typed spec', 'expected a number');

// ------------------------------------------------------------------ shop list
$a = Inventory::createComponent($uid, ['component_type' => 'SADDLE', 'label' => 'Saddle', 'shop' => '  Bike-Components.de ']);
$b = Inventory::createComponent($uid, ['component_type' => 'STEM', 'label' => 'Stem', 'shop' => 'bike-components.de']);
check(Db::value('SELECT shop FROM components WHERE id = ?', [$b]) === 'Bike-Components.de', 'a name in other case is stored in the list spelling');
check(PickLists::names($uid) === ['Bike-Components.de'], 'one name on the list');
$c = Inventory::createComponent($uid, ['component_type' => 'BAR_TAPE', 'label' => 'Tape', 'shop' => 'BC']);
$rows = PickLists::rows($uid, 'SHOP');
$byName = array_column($rows, null, 'name');
check($byName['Bike-Components.de']['uses'] === 2, 'usage count per name');
PickLists::merge($uid, (int)$byName['BC']['id'], (int)$byName['Bike-Components.de']['id']);
check(Db::value('SELECT shop FROM components WHERE id = ?', [$c]) === 'Bike-Components.de', 'merge moves the records');
$d = Inventory::createComponent($uid, ['component_type' => 'BAR_TAPE', 'label' => 'Tape 2', 'shop' => 'bc']);
check(Db::value('SELECT shop FROM components WHERE id = ?', [$d]) === 'Bike-Components.de', 'a merged name typed again gives the kept name');
PickLists::rename($uid, (int)$byName['Bike-Components.de']['id'], 'bike-components');
check((int)Db::value("SELECT COUNT(*) FROM components WHERE user_id = ? AND shop = 'bike-components'", [$uid]) === 4, 'rename: every record follows');
check_throws(fn() => PickLists::add($uid, 'SHOP', 'BIKE-COMPONENTS'), 'duplicate name refused', 'already');
PickLists::hide($uid, (int)$byName['Bike-Components.de']['id'], true);
check(PickLists::names($uid) === [], 'hidden name is not offered');
check(Db::value('SELECT shop FROM components WHERE id = ?', [$a]) === 'bike-components', 'hidden name stays on its records');

// ------------------------------------------------------------------ change log
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Log bike', 'created_at' => $now, 'updated_at' => $now]);
Domain::install($uid, $a, $bike, null, 'SADDLE', '2026-05-01');
Db::updateOwned('components', $a, $uid, ['label' => 'Saddle Fizik', 'price_cents' => 12000, 'updated_at' => now_utc()]);
$log = ChangeLog::entries($uid, null, $a);
$fields = array_column(array_filter($log, fn($e) => $e['action'] === 'CHANGED'), 'new_value', 'field');
check(($fields['label'] ?? '') === 'Saddle Fizik' && ($fields['price_cents'] ?? '') === '120.00', 'edits are logged field by field (money shown in euro)');
check((bool)array_filter($log, fn($e) => $e['entity'] === 'installation' && str_contains((string)$e['new_value'], 'On Log bike')), 'fitting is logged on the part');
check((bool)array_filter(ChangeLog::entries($uid, $bike), fn($e) => $e['entity'] === 'bike' && $e['action'] === 'CREATED'), 'new bike logged');
$inst = (int)Db::value('SELECT id FROM installations WHERE component_id = ?', [$a]);
Domain::remove($uid, $inst, '2026-06-01', 'worn');
check((bool)array_filter(ChangeLog::entries($uid, null, $a), fn($e) => str_contains((string)$e['new_value'], 'Taken off on 2026-06-01')), 'taking a part off is logged');
check((bool)array_filter(ChangeLog::entries($uid, null, null, 'list'), fn($e) => str_contains((string)$e['new_value'], 'Renamed')), 'list rename logged');
Db::updateOwned('components', $a, $uid, ['label' => 'Saddle Fizik', 'updated_at' => now_utc()]);
check(count(ChangeLog::entries($uid, null, $a)) === count($log) + 1, 'saving without a change logs nothing new');

// ------------------------------------------------------------------ pages
$w = new Browser($base);
$w->post('r=login', ['email' => 'products@example.test', 'password' => 'product-person-pw']);
foreach (['r=products', "r=product&id=$pid", 'r=product_edit', "r=product_edit&id=$pid", 'r=product_import', 'r=lists', 'r=changes', "r=changes&part=$a",
    "r=changes&bike=$bike", 'r=parts', "r=part&id=$a", "r=bike&id=$bike"] as $pg) {
    $w->get($pg);
    check($w->status === 200 && !str_contains($w->body, 'Something went wrong'), "page $pg renders (status {$w->status})");
}
check(str_contains($w->body, '<datalist id="shops">'), 'shop names offered in a datalist');
$w->get('r=product_template&type=CHAIN&kind=schema');
check($w->status === 200 && (json_decode($w->body, true)['properties']['specs']['properties']['speeds']['type'] ?? '') === 'integer', 'schema download');
$w->get('r=product_template&kind=instructions');
check($w->status === 200 && str_contains($w->body, '# Instructions: write a script'), 'instructions download');
$w->post('r=product_edit', ['component_type' => 'TIRE', 'maker' => 'Continental', 'model' => 'GP5000 S TR 700x28c', 'list_price' => '64,95', 'specs' => "width_mm: 28\nfoo: bar"]);
$tp = Inventory::findProduct($uid, 'TIRE', 'Continental', 'GP5000 S TR 700x28c');
check($tp && (int)$tp['list_price_cents'] === 6495 && json_decode($tp['specs_json'], true)['foo'] === 'bar', 'product typed in a form');
$w->post("r=product&id={$tp['id']}", ['do' => 'spare', 'label' => 'GP5000 #1', 'price' => '50', 'shop' => 'bike-components']);
check((int)Db::value('SELECT product_id FROM components WHERE user_id = ? AND label = ?', [$uid, 'GP5000 #1']) === (int)$tp['id'], 'spare added from the product page');
// upload: check, then import
$good = '{"component_type":"CASSETTE","maker":"Shimano","model":"CS-R8100-12 11-34","specs":{"speeds":12,"range":"11-34"}}';
$bad = '{"component_type":"CASSETTE","maker":"Shimano","model":"X","specs":{"speeds":"lots"}}';
$w->upload('r=product_import', ['do' => 'check'], ['files' => [['good.json', $good], ['bad.json', $bad]]]);
check($w->status === 200 && str_contains($w->body, 'products[0]') === false && str_contains($w->body, 'file.specs.speeds'), 'check lists the error with its place');
check(!Inventory::findProduct($uid, 'CASSETTE', 'Shimano', 'CS-R8100-12 11-34'), 'check alone imports nothing');
preg_match_all('/name="token\[\]" value="([a-f0-9]{32})"/', $w->body, $m);
check(count($m[1]) === 1, 'only the good file can be imported');
$w->post('r=product_import', ['do' => 'import', 'token' => $m[1]]);
check((bool)Inventory::findProduct($uid, 'CASSETTE', 'Shimano', 'CS-R8100-12 11-34'), 'import after the check');
$w->post('r=product_import', ['do' => 'import', 'token' => $m[1]]);
check(str_contains($w->body, 'gone'), 'a token works once');
$w->post('r=lists', ['do' => 'add', 'name' => 'Local shop']);
check(in_array('Local shop', PickLists::names($uid), true), 'shop added on the list page');
// another user sees nothing
$o = new Browser($base);
$o->post('r=login', ['email' => 'r2other@example.test', 'password' => 'round-two-other']);
$o->get("r=product&id=$pid");
check($o->status === 404, 'other user cannot see my product');
$o->get('r=changes');
check(!str_contains($o->body, 'Saddle Fizik'), 'other user does not see my change log');
$o->post('r=product_import', ['do' => 'import', 'token' => ['0123456789abcdef0123456789abcdef']]);
check(!str_contains($o->body, 'Something went wrong'), 'unknown token handled');
