<?php
declare(strict_types=1);

// Languages: every UI text has a German version, placeholders survive, numbers use a decimal comma in German,
// the switch at the top changes the language (saved per user, a cookie for visitors), and the pages render in German
// without English text left over.

require_once $root . '/tools/i18n_keys.php';

// ------------------------------------------------------------------ the dictionary
$de = I18n::dict('de');
$keys = i18n_all_keys($root);
$missing = array_values(array_filter($keys, fn($k) => i18n_needs_translation($k) && !array_key_exists($k, $de)));
check($missing === [], 'every UI text has a German version; missing: ' . implode(' | ', array_slice($missing, 0, 10)));
$ph = function (string $s): array {
    preg_match_all('/\{\w+\}/', $s, $m);
    sort($m[0]);
    return $m[0];
};
$badPh = [];
foreach ($de as $en => $text) {
    if ($ph((string)$en) !== $ph((string)$text)) {
        $badPh[] = $en;
    }
}
check($badPh === [], 'German texts keep the same {placeholders}; wrong: ' . implode(' | ', array_slice($badPh, 0, 5)));
$unused = array_diff(array_keys($de), $keys);
check($unused === [], 'no German text for a key the app no longer uses: ' . implode(' | ', array_slice($unused, 0, 5)));

// ------------------------------------------------------------------ the helpers
check(I18n::lang() === 'en', 'the command line runs in English');
check(t('Bikes') === 'Bikes' && t('No such text {x}', ['x' => 1]) === 'No such text 1', 'English: the key is the text, placeholders filled');
I18n::with('de', function () {
    check(t('Bikes') === 'Räder', 'German: Bikes → Räder');
    check(t('Edit {name}', ['name' => 'Synapse']) === 'Synapse bearbeiten', 'German: placeholders can move');
    check(t('A text nobody translated') === 'A text nobody translated', 'German: a missing text falls back to English');
    check(num(1234.5, 1) === '1 234,5' && km(12.5, 1) === '12,5 km', 'German numbers use a decimal comma');
    check(parse_number('12,5', 'Km') == 12.5 && parse_number('1 234,5', 'Km') == 1234.5, 'German decimal input is read');
    check(tn('{n} ride changed.', '{n} rides changed.', 1) === '1 Fahrt geändert.' && tn('{n} ride changed.', '{n} rides changed.', 3) === '3 Fahrten geändert.', 'plurals');
    check(plural_word('tube', 2) === 'Schläuche' && plural_word('tube', 1) === 'Schlauch', 'German noun plurals');
    check(lc('Chain') === 'Chain', 'German nouns keep their capital letter');
    check(Catalog::typeName('CHAIN') === 'Kette' && Catalog::actionName('HOT_WAX') !== 'Hot wax', 'catalog names are translated');
});
check(I18n::lang() === 'en' && num(1234.5, 1) === '1 234.5' && lc('Chain') === 'chain', 'back to English after with()');

// ------------------------------------------------------------------ the switch for a visitor (cookie)
$visitor = new Browser($base);
$page = $visitor->get('r=login');
check(str_contains($page, '<html lang="en">') && str_contains($page, 'Sign in'), 'a visitor without a choice sees English');
$visitor->post('r=set_lang', ['lang' => 'de']);
check(str_contains($visitor->body, '<html lang="de">') && str_contains($visitor->body, 'Anmelden'), 'the switch shows the sign-in page in German');
$visitor->get('r=register');
check(str_contains($visitor->body, '<html lang="de">'), 'the choice is remembered (cookie)');
$visitor->post('r=set_lang', ['lang' => 'xx']);
check(str_contains($visitor->body, '<html lang="de">'), 'an unknown language changes nothing');

// ------------------------------------------------------------------ a signed-in user: saved on the account
$now = now_utc();
$uid = Db::insert('users', ['email' => 'sprache@example.test', 'display_name' => 'Sprache', 'password_hash' => Auth::hash('sprache-tester-pw'),
    'role' => 'ADMIN', 'status' => 'ACTIVE', 'email_verified_at' => $now, 'timezone' => 'Europe/Berlin', 'lang' => 'de', 'created_at' => $now, 'updated_at' => $now]);
Domain::seedUser($uid);
$bike = Db::insert('bikes', ['user_id' => $uid, 'name' => 'Roadmachine', 'created_at' => $now, 'updated_at' => $now]);
$chain = Inventory::createComponent($uid, ['component_type' => 'CHAIN', 'label' => 'Kette Eins', 'prior_usage' => 'NEW']);
Domain::install($uid, $chain, $bike, null, 'CHAIN', '2026-03-01');
$tire = Inventory::createComponent($uid, ['component_type' => 'TIRE', 'label' => 'Reifen Vorne', 'prior_usage' => 'NEW']);
$rideId = Db::insert('rides', ['user_id' => $uid, 'bike_id' => $bike, 'ride_date' => '2026-03-10', 'distance_km' => 42.5, 'duration_s' => 5400,
    'kind' => 'OUTDOOR', 'created_at' => $now, 'updated_at' => $now]);

$u = new Browser($base);
$u->post('r=login', ['email' => 'sprache@example.test', 'password' => 'sprache-tester-pw']);
$home = $u->get('r=home');
check(str_contains($home, '<html lang="de">') && str_contains($home, 'Abmelden'), 'the account language (German) is used after sign-in');

// every page in German, with no English UI text left over
$english = [];
foreach ($de as $en => $text) {
    if ($en !== $text && preg_match('/[A-Za-z]{4,}/', (string)$en) && !str_contains((string)$en, '{') && !str_starts_with((string)$en, 'plural:')) {
        $english[(string)$en] = true;
    }
}
$pages = ['home', 'reminders', 'bikes', "bike&id=$bike", "bike_edit&id=$bike", 'parts', "part&id=$chain", "part&id=$tire", 'part_edit',
    'rides', "ride&id=$rideId", 'ride_import', 'maintenance', 'log', 'rules', 'supplies', 'supply_edit', 'groupset', 'spares', 'my_settings',
    'punctures', "costs&bike=$bike", 'bundles', 'repairs', 'part_life', 'products', 'product_edit', 'product_import', 'lists', 'changes',
    'backups', 'fresh_start', 'diagnostics', 'account', "part_replace&id=$chain", "group_wheels&bike=$bike", 'chains',
    'admin', 'admin_users', 'admin_audit', 'admin_settings', 'admin_system'];
foreach ($pages as $p) {
    $body = $u->get('r=' . $p);
    if ($u->status === 404 && str_contains($body, 'Diese Seite gibt es nicht')) {
        continue; // route name not used by this version
    }
    check($u->status === 200 && str_contains($body, '<html lang="de">'), "page $p renders in German (status {$u->status})");
    if ($p === 'admin_users') {
        continue; // lists the earlier tests' users, whose names ("Rides", "Costs" ...) are data, not UI text
    }
    $visible = preg_replace(['#<script\b.*?</script>#s', '#<style\b.*?</style>#s', '#<code>.*?</code>#s', '#<option[^>]*>#'], ' ', $body);
    $left = [];
    foreach (preg_split('/<[^>]+>/', (string)$visible) as $node) {
        $node = trim(html_entity_decode($node, ENT_QUOTES | ENT_HTML5));
        if ($node !== '' && isset($english[$node])) {
            $left[] = $node;
        }
    }
    check($left === [], "page $p has no English UI text left: " . implode(' | ', array_slice(array_unique($left), 0, 8)));
}

// switching back to English is saved on the account
$u->post('r=set_lang', ['lang' => 'en']);
check(str_contains($u->body, '<html lang="en">') && str_contains($u->body, 'Sign out'), 'switching to English shows English');
check(Db::value('SELECT lang FROM users WHERE id = ?', [$uid]) === 'en', 'the choice is saved on the account');
$u->post('r=my_settings', ['lang' => 'de', 'spoke_relace_after' => '3', 'default_tire_setup' => 'TUBE']);
check(Db::value('SELECT lang FROM users WHERE id = ?', [$uid]) === 'de' && str_contains($u->body, 'Einstellungen gespeichert.'), 'My settings can set the language too');
