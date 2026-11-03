<?php
declare(strict_types=1);

// Lists every text the app translates: t('...') / tn('...', '...') literals in app/ and the catalog's
// names and labels. Used by the test suite (every key needs a German text) and when adding a language:
//   php tools/i18n_keys.php            → one key per line
//   php tools/i18n_keys.php --missing de   → only keys without a translation in app/lang/de.php
// Keys without a word of 3+ letters ("10-28", "140 mm") may stay as they are and are never "missing".

$root = dirname(__DIR__);

function i18n_code_keys(string $root): array
{
    $keys = [];
    $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root . '/app'));
    foreach ($it as $f) {
        if (!$f->isFile() || $f->getExtension() !== 'php' || str_contains($f->getPathname(), '/lang/')) {
            continue;
        }
        $toks = array_values(array_filter(token_get_all((string)file_get_contents($f->getPathname())),
            fn($t) => !is_array($t) || !in_array($t[0], [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)));
        foreach ($toks as $i => $tk) {
            if (!is_array($tk) || $tk[0] !== T_STRING || !in_array($tk[1], ['t', 'tn'], true) || ($toks[$i + 1] ?? null) !== '(') {
                continue;
            }
            $prev = $toks[$i - 1] ?? null;
            if (is_array($prev) && in_array($prev[0], [T_FUNCTION, T_OBJECT_OPERATOR, T_DOUBLE_COLON, T_NULLSAFE_OBJECT_OPERATOR], true)) {
                continue;
            }
            $args = $tk[1] === 'tn' ? [$i + 2, $i + 4] : [$i + 2];
            foreach ($args as $a) {
                $lit = $toks[$a] ?? null;
                $after = $toks[$a + 1] ?? null;
                if (is_array($lit) && $lit[0] === T_CONSTANT_ENCAPSED_STRING && in_array($after, [',', ')'], true)) {
                    $keys[eval('return ' . $lit[1] . ';')] = true;
                }
            }
        }
    }
    return array_keys($keys);
}

function i18n_catalog_keys(string $root): array
{
    $d = json_decode((string)file_get_contents($root . '/app/catalog.json'), true);
    $k = [];
    $label = fn(string $code) => ucfirst(strtolower(str_replace('_', ' ', $code)));
    foreach ($d['component_types'] as $t) {
        $k[] = $t['name'];
        $k[] = 'plural:' . $t['name'];
        $k[] = $t['category'];
        foreach ($t['slots'] as $s) {
            $k[] = $label($s);
        }
    }
    $k[] = $label('OTHER');
    foreach ($d['actions'] as $a) {
        $k[] = $a['name'];
        foreach ($a['outcomes'] as $o) {
            $k[] = $label($o);
        }
    }
    foreach ($d['default_rules'] as $r) {
        $k[] = $r['name'];
        if ($r['requires_setup']) {
            $k[] = strtolower($r['requires_setup']);
        }
    }
    foreach (['dispositions', 'incident_types', 'tire_setups'] as $list) {
        foreach ($d[$list] as $v) {
            $k[] = $v;
        }
    }
    foreach ($d['stock_units'] as [$unit, $help]) {
        $k[] = $unit;
        $k[] = 'plural:' . $unit;
        $k[] = $help;
    }
    foreach ($d['incident_options'] as $opts) {
        foreach ($opts as $o) {
            $k[] = $o['label'];
        }
    }
    foreach ($d['product_spec_fields'] as $fields) {
        foreach ($fields as $f) {
            if ((string)$f['description'] !== '') {
                $k[] = $f['description'];
            }
        }
    }
    foreach ($d['groupset_templates'] as $t) {
        foreach ($t['options'] as $o) {
            $k[] = $o['label'];
            foreach ($o['choices'] as $c) {
                $k[] = $c['label'];
            }
        }
    }
    foreach (['DRY', 'WET', 'MANUFACTURER', 'PERSONAL', 'DEFAULT'] as $c) {
        $k[] = $label($c);
    }
    return array_values(array_unique($k));
}

/** Texts kept in PHP constants and shown through t() / t_list(). */
function i18n_constant_keys(string $root): array
{
    require_once $root . '/app/core.php';
    require_once $root . '/app/i18n.php';
    foreach (['catalog', 'chains', 'groupsets', 'money', 'records', 'workshop', 'domain', 'inventory', 'backups'] as $f) {
        require_once $root . '/app/' . $f . '.php';
    }
    $k = array_merge(array_values(Catalog::CONSUMABLE_KINDS), array_values(Groupsets::OCCUPIED), array_values(ServiceOrders::OUTCOMES),
        array_values(Workshop::FIT_TEXT), array_values(ChangeLog::ENTITY_LABELS), array_column(PickLists::LISTS, 'hint'), array_column(PickLists::LISTS, 'name'));
    return array_values(array_unique($k));
}

function i18n_all_keys(string $root): array
{
    return array_values(array_unique(array_merge(i18n_code_keys($root), i18n_catalog_keys($root), i18n_constant_keys($root))));
}

function i18n_needs_translation(string $key): bool
{
    return (bool)preg_match('/[A-Za-z]{3,}/', $key);
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === realpath(__FILE__)) {
    $keys = i18n_all_keys($root);
    if (($argv[1] ?? '') === '--missing') {
        $dict = require $root . '/app/lang/' . preg_replace('/[^a-z]/', '', $argv[2] ?? 'de') . '.php';
        $keys = array_values(array_filter($keys, fn($k) => i18n_needs_translation($k) && !array_key_exists($k, $dict)));
    }
    sort($keys);
    echo implode("\n", array_map(fn($k) => json_encode($k, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $keys)), "\n";
}
