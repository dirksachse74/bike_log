<?php
declare(strict_types=1);

// Products (what you can buy: maker + model + specs) and the JSON product import, ported from
// backend/bikelog/services/product_import.py. Same file format (bikelog.product.v1 / bikelog.products.v1),
// so files written for the desktop app import here unchanged.
//
// - the whole file is checked first; with any error nothing is written and every error is listed with
//   its place (products[2].specs.speeds)
// - a product is identified by part type + maker + model (upper/lower case ignored): the same file twice
//   changes nothing; a changed file updates that product (specs merged: keys in the file win, keys only
//   in the app are kept)
// - items are physical parts you own (added as spares), identified by their label; an existing label is left alone

final class Products
{
    public const FORMAT = 'bikelog.product.v1';
    public const LIST_FORMAT = 'bikelog.products.v1';
    public const MAX_PRODUCTS = 2000;
    public const MAX_BYTES = 5 * 1024 * 1024;
    private const TOP_KEYS = ['format', 'component_type', 'maker', 'model', 'list_price', 'currency', 'specs', 'source', 'verified', 'notes', 'items'];
    private const ITEM_KEYS = ['label', 'price', 'purchase_date', 'prior_usage', 'serial_number', 'storage_location', 'notes'];
    private const SOURCE_KEYS = ['url', 'retrieved_at', 'tool'];
    private const KIND_TYPES = ['string' => 'string', 'integer' => 'integer', 'number' => 'number', 'boolean' => 'boolean', 'enum' => 'string'];

    /** Spec fields of a part type (shared with the desktop app through catalog.json). */
    public static function specFields(string $type): array
    {
        return Catalog::raw('product_spec_fields')[$type] ?? [];
    }

    // ------------------------------------------------------------------ templates

    public static function schema(string $type): array
    {
        $t = Catalog::type($type) ?? throw new NotFound('Unknown part type.');
        $props = [];
        foreach (self::specFields($type) as $f) {
            $p = ['type' => self::KIND_TYPES[$f['kind']], 'description' => $f['description'] . ($f['unit'] ? " ({$f['unit']})" : '')];
            if ($f['values']) {
                $p['enum'] = $f['values'];
            }
            $props[$f['key']] = $p;
        }
        return [
            '$schema' => 'https://json-schema.org/draft/2020-12/schema',
            '$id' => 'bikelog/product-templates/' . strtolower($type) . '.schema.json',
            'title' => 'Bike Log product: ' . $t['name'],
            'description' => 'One product (what you can buy) and optionally physical items you own. Only component_type, maker and model are required. Unlisted spec keys are imported too.',
            'type' => 'object',
            'required' => ['component_type', 'maker', 'model'],
            'additionalProperties' => false,
            'properties' => [
                'format' => ['const' => self::FORMAT],
                'component_type' => ['const' => $type],
                'maker' => ['type' => 'string', 'minLength' => 1],
                'model' => ['type' => 'string', 'minLength' => 1, 'description' => 'Model name or number, unique per maker'],
                'list_price' => ['type' => 'number', 'minimum' => 0, 'description' => 'Reference price in euro (not money spent)'],
                'currency' => ['const' => 'EUR'],
                'specs' => ['type' => 'object', 'properties' => $props ?: new stdClass(), 'additionalProperties' => true],
                'source' => ['type' => 'object', 'additionalProperties' => false, 'properties' => [
                    'url' => ['type' => 'string'], 'retrieved_at' => ['type' => 'string', 'format' => 'date'],
                    'tool' => ['type' => 'string', 'description' => 'Script name and version']]],
                'verified' => ['type' => 'boolean', 'description' => "true only if checked against the maker's documentation"],
                'notes' => ['type' => 'string'],
                'items' => ['type' => 'array', 'description' => 'Physical parts you own of this product (added as spares)',
                    'items' => ['type' => 'object', 'required' => ['label'], 'additionalProperties' => false, 'properties' => [
                        'label' => ['type' => 'string', 'minLength' => 1],
                        'price' => ['type' => 'number', 'minimum' => 0, 'description' => 'Price paid in euro'],
                        'purchase_date' => ['type' => 'string', 'format' => 'date'],
                        'prior_usage' => ['enum' => ['NEW', 'UNKNOWN']],
                        'serial_number' => ['type' => 'string'],
                        'storage_location' => ['type' => 'string'],
                        'notes' => ['type' => 'string']]]],
            ],
        ];
    }

    public static function example(string $type): array
    {
        $t = Catalog::type($type) ?? throw new NotFound('Unknown part type.');
        $specs = [];
        foreach (self::specFields($type) as $f) {
            if ($f['example'] !== null) {
                $specs[$f['key']] = $f['example'];
            }
        }
        $n = mb_strtolower($t['name']);
        return [
            'format' => self::FORMAT, 'component_type' => $type, 'maker' => 'Example maker', 'model' => "Example $n 1",
            'list_price' => 49.9, 'currency' => 'EUR', 'specs' => $specs ?: new stdClass(),
            'source' => ['url' => 'https://example.com/product-page', 'retrieved_at' => '2026-10-25', 'tool' => 'my-scraper 1.0'],
            'verified' => false, 'notes' => 'Optional free text',
            'items' => [['label' => "Spare $n 1", 'price' => 44.9, 'purchase_date' => '2026-10-20', 'prior_usage' => 'NEW', 'storage_location' => 'Workshop drawer']],
        ];
    }

    public static function json(mixed $v): string
    {
        return json_encode($v, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION) . "\n";
    }

    // ------------------------------------------------------------------ validation

    public static function parse(string $content): mixed
    {
        if (strlen($content) > self::MAX_BYTES) {
            throw new UserError('The file is larger than 5 MB.');
        }
        if (str_starts_with($content, "\xEF\xBB\xBF")) {
            $content = substr($content, 3);
        }
        if (!mb_check_encoding($content, 'UTF-8')) {
            throw new UserError('The file is not UTF-8 text.');
        }
        try {
            return json_decode($content, false, 64, JSON_THROW_ON_ERROR | JSON_BIGINT_AS_STRING);
        } catch (JsonException $e) {
            throw new UserError('Not valid JSON: ' . $e->getMessage() . '.');
        }
    }

    /** Objects are decoded as stdClass so {} and [] stay apart; this turns one into an array of its fields. */
    private static function obj(mixed $v): ?array
    {
        return $v instanceof stdClass ? get_object_vars($v) : null;
    }

    private static function isDate(mixed $v): bool
    {
        return is_string($v) && preg_match('/^\d{4}-\d{2}-\d{2}$/', $v) && checkdate((int)substr($v, 5, 2), (int)substr($v, 8, 2), (int)substr($v, 0, 4));
    }

    private static function typeOf(mixed $v): string
    {
        return match (true) { is_string($v) => 'text', is_int($v), is_float($v) => 'number', is_bool($v) => 'true/false',
            is_array($v) => 'list', $v === null => 'null', default => 'object' };
    }

    private static function repr(mixed $v): string
    {
        return json_encode($v, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '?';
    }

    /** Scrapers often give numbers as text ("1,8 mm" is not accepted, "1,8" is). */
    private static function coerce(array $f, mixed $v, string $where, array &$errors, array &$warnings): mixed
    {
        if ($v === null) {
            return null;
        }
        $unit = $f['unit'] ? " in {$f['unit']}" : '';
        if ($f['kind'] === 'number' || $f['kind'] === 'integer') {
            if (is_bool($v)) {
                $errors[] = "$where: expected a number, got true/false";
                return null;
            }
            if (is_string($v)) {
                $t = str_replace(',', '.', trim($v));
                if (!is_numeric($t)) {
                    $errors[] = "$where: expected a number$unit, got " . self::repr($v);
                    return null;
                }
                $warnings[] = "$where: text " . self::repr($v) . ' read as a number';
                $v = (float)$t;
            }
            if (!is_int($v) && !is_float($v)) {
                $errors[] = "$where: expected a number, got " . self::typeOf($v);
                return null;
            }
            if ($f['kind'] === 'integer') {
                if ((float)$v != floor((float)$v)) {
                    $errors[] = "$where: expected a whole number, got $v";
                    return null;
                }
                return (int)$v;
            }
            return $v;
        }
        if ($f['kind'] === 'boolean') {
            if (is_bool($v)) {
                return $v;
            }
            if (is_string($v) && in_array(strtolower(trim($v)), ['true', 'yes', 'false', 'no'], true)) {
                $warnings[] = "$where: text " . self::repr($v) . ' read as true/false';
                return in_array(strtolower(trim($v)), ['true', 'yes'], true);
            }
            $errors[] = "$where: expected true or false, got " . self::repr($v);
            return null;
        }
        if (!is_string($v) && !is_int($v) && !is_float($v)) {
            $errors[] = "$where: expected text, got " . self::typeOf($v);
            return null;
        }
        $v = trim((string)$v);
        if ($f['kind'] === 'enum' && !in_array($v, $f['values'], true)) {
            $match = null;
            foreach ($f['values'] as $x) {
                if (mb_strtolower($x) === mb_strtolower($v)) {
                    $match = $x;
                }
            }
            if ($match === null) {
                $errors[] = "$where: " . self::repr($v) . ' is not one of ' . implode(', ', $f['values']);
                return null;
            }
            $v = $match;
        }
        return $v;
    }

    private static function money(mixed $v, string $where, array &$errors): ?int
    {
        if ($v === null) {
            return null;
        }
        if (is_bool($v) || (!is_int($v) && !is_float($v)) || $v < 0) {
            $errors[] = "$where: expected an amount in euro such as 49.9";
            return null;
        }
        return (int)round($v * 100);
    }

    /** Check a whole file: normalised products, errors and warnings. Never writes. */
    public static function validate(mixed $doc): array
    {
        $errors = [];
        $warnings = [];
        $top = self::obj($doc);
        if (is_array($doc)) {
            $raw = $doc;
        } elseif ($top !== null && array_key_exists('products', $top)) {
            if (($top['format'] ?? self::LIST_FORMAT) !== self::LIST_FORMAT) {
                return ['products' => [], 'errors' => ['Unsupported format ' . self::repr($top['format']) . '; expected "' . self::LIST_FORMAT . '"'], 'warnings' => []];
            }
            if (!is_array($top['products'])) {
                return ['products' => [], 'errors' => ["'products' must be a list"], 'warnings' => []];
            }
            $raw = $top['products'];
        } elseif ($top !== null) {
            $raw = [$doc];
        } else {
            return ['products' => [], 'errors' => ['The file must contain a JSON object or a list of objects'], 'warnings' => []];
        }
        if (count($raw) > self::MAX_PRODUCTS) {
            return ['products' => [], 'errors' => ['Too many products in one file (max ' . self::MAX_PRODUCTS . ')'], 'warnings' => []];
        }
        $multi = !($top !== null && !array_key_exists('products', $top));
        $types = Catalog::types();
        $out = [];
        $seen = [];
        $labels = [];
        foreach ($raw as $n => $pv) {
            $at = $multi ? "products[$n]" : 'file';
            $before = count($errors);
            $p = self::obj($pv);
            if ($p === null) {
                $errors[] = "$at: expected an object";
                continue;
            }
            $unknown = array_diff(array_keys($p), self::TOP_KEYS);
            if ($unknown) {
                sort($unknown);
                $errors[] = "$at: unknown fields " . implode(', ', $unknown) . " (put product data under 'specs')";
            }
            if (($p['format'] ?? self::FORMAT) !== self::FORMAT) {
                $errors[] = "$at.format: expected \"" . self::FORMAT . '"';
            }
            $ctype = $p['component_type'] ?? null;
            $known = is_string($ctype) && isset($types[$ctype]);
            if (!$known) {
                $errors[] = "$at.component_type: " . self::repr($ctype) . ' is not a Bike Log part type (one of ' . implode(', ', array_keys($types)) . ')';
            }
            $maker = $p['maker'] ?? null;
            $model = $p['model'] ?? null;
            foreach (['maker' => $maker, 'model' => $model] as $k => $val) {
                if (!is_string($val) || trim($val) === '') {
                    $errors[] = "$at.$k: required text";
                }
            }
            if (($p['currency'] ?? 'EUR') !== 'EUR') {
                $errors[] = "$at.currency: only EUR is supported; convert prices before importing";
            }
            $listPrice = self::money($p['list_price'] ?? null, "$at.list_price", $errors);
            $specsIn = $p['specs'] ?? null;
            $specs = [];
            if ($specsIn !== null && self::obj($specsIn) === null) {
                $errors[] = "$at.specs: expected an object";
            }
            $fields = [];
            foreach ($known ? self::specFields($ctype) : [] as $f) {
                $fields[$f['key']] = $f;
            }
            $extra = [];
            foreach (self::obj($specsIn) ?? [] as $k => $v) {
                if (isset($fields[$k])) {
                    $val = self::coerce($fields[$k], $v, "$at.specs.$k", $errors, $warnings);
                    if ($val !== null) {
                        $specs[$k] = $val;
                    }
                } elseif (is_scalar($v) || $v === null) {
                    $extra[] = $k;
                    if ($v !== null) {
                        $specs[$k] = $v;
                    }
                } else {
                    $errors[] = "$at.specs.$k: values must be text, numbers or true/false";
                }
            }
            if ($extra) {
                $warnings[] = "$at.specs: kept fields not in the template: " . implode(', ', $extra);
            }
            $source = [];
            if (($p['source'] ?? null) !== null) {
                $source = self::obj($p['source']);
                if ($source === null) {
                    $errors[] = "$at.source: expected an object";
                    $source = [];
                }
            }
            $bad = array_diff(array_keys($source), self::SOURCE_KEYS);
            if ($bad) {
                sort($bad);
                $errors[] = "$at.source: unknown fields " . implode(', ', $bad);
            }
            if (($source['retrieved_at'] ?? null) !== null && !self::isDate($source['retrieved_at'])) {
                $errors[] = "$at.source.retrieved_at: expected a date like 2026-10-25";
            }
            foreach (['url', 'tool'] as $k) {
                if (isset($source[$k]) && !is_string($source[$k])) {
                    $errors[] = "$at.source.$k: expected text";
                }
            }
            $verified = $p['verified'] ?? false;
            if (!is_bool($verified)) {
                $errors[] = "$at.verified: expected true or false";
            }
            $notes = $p['notes'] ?? null;
            if ($notes !== null && !is_string($notes)) {
                $errors[] = "$at.notes: expected text";
            }
            $items = [];
            $itemsIn = $p['items'] ?? null;
            if ($itemsIn !== null && !is_array($itemsIn)) {
                $errors[] = "$at.items: expected a list";
                $itemsIn = [];
            }
            foreach ($itemsIn ?? [] as $i => $iv) {
                $iat = "$at.items[$i]";
                $it = self::obj($iv);
                if ($it === null) {
                    $errors[] = "$iat: expected an object";
                    continue;
                }
                $bad = array_diff(array_keys($it), self::ITEM_KEYS);
                if ($bad) {
                    sort($bad);
                    $errors[] = "$iat: unknown fields " . implode(', ', $bad);
                }
                $label = $it['label'] ?? null;
                if (!is_string($label) || trim($label) === '') {
                    $errors[] = "$iat.label: required text, e.g. 'Spare chain 1'";
                    continue;
                }
                $key = $ctype . '|' . mb_strtolower(trim($label));
                if (isset($labels[$key])) {
                    $errors[] = "$iat.label: " . self::repr($label) . " is used twice in this file (also {$labels[$key]})";
                }
                $labels[$key] = $iat;
                if (($it['purchase_date'] ?? null) !== null && !self::isDate($it['purchase_date'])) {
                    $errors[] = "$iat.purchase_date: expected a date like 2026-10-25";
                }
                if (!in_array($it['prior_usage'] ?? 'NEW', ['NEW', 'UNKNOWN'], true)) {
                    $errors[] = "$iat.prior_usage: NEW or UNKNOWN";
                }
                foreach (['serial_number', 'storage_location', 'notes'] as $k) {
                    if (isset($it[$k]) && !is_string($it[$k])) {
                        $errors[] = "$iat.$k: expected text";
                    }
                }
                $items[] = ['label' => trim($label), 'price_cents' => self::money($it['price'] ?? null, "$iat.price", $errors),
                    'purchase_date' => $it['purchase_date'] ?? null, 'prior_usage' => $it['prior_usage'] ?? 'NEW',
                    'serial_number' => $it['serial_number'] ?? null, 'storage_location' => $it['storage_location'] ?? null, 'notes' => $it['notes'] ?? null];
            }
            if (count($errors) > $before) {
                continue;
            }
            $ident = $ctype . '|' . mb_strtolower(trim($maker)) . '|' . mb_strtolower(trim($model));
            if (isset($seen[$ident])) {
                $errors[] = "$at: same product as {$seen[$ident]} ($maker $model)";
                continue;
            }
            $seen[$ident] = $at;
            $out[] = ['at' => $at, 'component_type' => $ctype, 'maker' => trim($maker), 'model' => trim($model), 'list_price_cents' => $listPrice,
                'specs' => $specs, 'source' => $source, 'verified' => $verified, 'notes' => $notes, 'items' => $items];
        }
        return ['products' => $out, 'errors' => $errors, 'warnings' => $warnings];
    }

    // ------------------------------------------------------------------ import

    private static function specVersion(array $p): string
    {
        $when = $p['source']['retrieved_at'] ?? gmdate('Y-m-d');
        $tool = !empty($p['source']['tool']) ? ' by ' . $p['source']['tool'] : '';
        return "JSON import $when$tool; " . ($p['verified'] ? 'verified' : 'unverified');
    }

    /** Validate, then create or update products and add items. With errors nothing is written. */
    public static function import(int $uid, mixed $doc, bool $dryRun = false): array
    {
        $v = self::validate($doc);
        $report = ['ok' => !$v['errors'], 'errors' => $v['errors'], 'warnings' => $v['warnings'], 'dry_run' => $dryRun, 'products' => [],
            'counts' => ['CREATED' => 0, 'UPDATED' => 0, 'UNCHANGED' => 0, 'ITEMS_CREATED' => 0, 'ITEMS_EXISTING' => 0]];
        if ($v['errors']) {
            return $report;
        }
        $run = function () use ($uid, $v, $dryRun, &$report) {
            $prevSource = ChangeLog::$source;
            ChangeLog::$source = 'PRODUCT_IMPORT';
            try {
                foreach ($v['products'] as $p) {
                    $prod = Inventory::findProduct($uid, $p['component_type'], $p['maker'], $p['model']);
                    $row = ['at' => $p['at'], 'component_type' => $p['component_type'], 'maker' => $p['maker'], 'model' => $p['model'], 'changed' => [], 'items' => []];
                    $specSource = $p['source']['url'] ?? 'JSON import';
                    if ($prod === null) {
                        $row['status'] = 'CREATED';
                        if (!$dryRun) {
                            $id = Db::insert('products', ['user_id' => $uid, 'component_type' => $p['component_type'], 'maker' => $p['maker'], 'model' => $p['model'],
                                'specs_json' => $p['specs'] ? json_encode($p['specs'], JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION) : null,
                                'spec_source' => mb_substr($specSource, 0, 500), 'spec_version' => mb_substr(self::specVersion($p), 0, 200), 'notes' => $p['notes'],
                                'list_price_cents' => $p['list_price_cents'], 'created_at' => now_utc()]);
                            $prod = Db::one('SELECT * FROM products WHERE id = ?', [$id]);
                        }
                    } else {
                        $old = json_decode((string)($prod['specs_json'] ?? ''), true) ?: [];
                        $merged = $p['specs'] + $old;
                        $changed = [];
                        foreach ($merged as $k => $val) {
                            if (!array_key_exists($k, $old) || $old[$k] !== $val) {
                                $changed[] = $k;
                            }
                        }
                        sort($changed);
                        $upd = [];
                        if ($changed) {
                            $upd['specs_json'] = json_encode($merged, JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
                        }
                        if ($p['list_price_cents'] !== null && $p['list_price_cents'] !== ($prod['list_price_cents'] === null ? null : (int)$prod['list_price_cents'])) {
                            $upd['list_price_cents'] = $p['list_price_cents'];
                            $changed[] = 'list_price';
                        }
                        if ($p['notes'] !== null && $p['notes'] !== $prod['notes']) {
                            $upd['notes'] = $p['notes'];
                            $changed[] = 'notes';
                        }
                        if (!empty($p['source']['url']) && $p['source']['url'] !== $prod['spec_source']) {
                            $upd['spec_source'] = mb_substr($specSource, 0, 500);
                            $changed[] = 'source';
                        }
                        if ($upd) {
                            $upd['spec_version'] = mb_substr(self::specVersion($p), 0, 200);
                        }
                        $row['status'] = $upd ? 'UPDATED' : 'UNCHANGED';
                        $row['changed'] = $changed;
                        if ($upd && !$dryRun) {
                            Db::updateOwned('products', (int)$prod['id'], $uid, $upd);
                        }
                    }
                    $report['counts'][$row['status']]++;
                    foreach ($p['items'] as $it) {
                        $existing = Db::one('SELECT id, product_id FROM components WHERE user_id = ? AND component_type = ? AND LOWER(label) = LOWER(?) ORDER BY id LIMIT 1',
                            [$uid, $p['component_type'], $it['label']]);
                        if ($existing) {
                            if ($prod !== null && $existing['product_id'] !== null && (int)$existing['product_id'] !== (int)$prod['id']) {
                                throw new UserError("{$p['at']}: a part labelled “{$it['label']}” already exists for another product; choose a different label.");
                            }
                            $row['items'][] = ['label' => $it['label'], 'status' => 'EXISTS', 'component_id' => (int)$existing['id']];
                            $report['counts']['ITEMS_EXISTING']++;
                            continue;
                        }
                        $cid = null;
                        if (!$dryRun) {
                            $cid = Inventory::createComponent($uid, ['component_type' => $p['component_type'], 'label' => $it['label'], 'product_id' => (int)$prod['id'],
                                'maker' => $p['maker'], 'model' => $p['model'], 'prior_usage' => $it['prior_usage'], 'price_cents' => $it['price_cents'],
                                'purchase_date' => $it['purchase_date'], 'serial_number' => $it['serial_number'] !== null ? mb_substr($it['serial_number'], 0, 120) : null,
                                'notes' => $it['notes'], 'storage_location' => $it['storage_location'] !== null ? mb_substr($it['storage_location'], 0, 160) : null]);
                        }
                        $row['items'][] = ['label' => $it['label'], 'status' => 'CREATED', 'component_id' => $cid];
                        $report['counts']['ITEMS_CREATED']++;
                    }
                    if ($prod !== null) {
                        $row['product_id'] = (int)$prod['id'];
                    }
                    $report['products'][] = $row;
                }
            } finally {
                ChangeLog::$source = $prevSource;
            }
        };
        if ($dryRun) {
            $run();
        } else {
            Db::tx($run);
        }
        return $report;
    }

    // ------------------------------------------------------------------ products in the app

    public static function get(int $uid, int $id): array
    {
        return Db::one('SELECT * FROM products WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Product not found.');
    }

    public static function name(array $p): string
    {
        return trim(($p['maker'] ?? '') . ' ' . $p['model']);
    }

    public static function rows(int $uid, string $type = ''): array
    {
        $sql = 'SELECT p.*, (SELECT COUNT(*) FROM components c WHERE c.product_id = p.id AND c.user_id = p.user_id) AS parts
            FROM products p WHERE p.user_id = ?';
        $params = [$uid];
        if ($type !== '') {
            $sql .= ' AND p.component_type = ?';
            $params[] = $type;
        }
        return Db::all($sql . ' ORDER BY p.component_type, p.maker, p.model', $params);
    }

    /** Specs typed as "key: value" lines. Known fields are checked like an import; other keys are kept as text. */
    public static function parseSpecLines(string $type, string $text): array
    {
        $fields = [];
        foreach (self::specFields($type) as $f) {
            $fields[$f['key']] = $f;
        }
        $specs = [];
        $errors = [];
        $warnings = [];
        foreach (preg_split('/\R/', $text) as $n => $line) {
            if (trim($line) === '') {
                continue;
            }
            if (!str_contains($line, ':')) {
                throw new UserError('Specs line ' . ($n + 1) . ': write it as “key: value”.');
            }
            [$k, $v] = array_map('trim', explode(':', $line, 2));
            $k = strtolower(preg_replace('/[^a-z0-9_]+/i', '_', $k));
            if ($k === '' || $v === '') {
                continue;
            }
            if (isset($fields[$k])) {
                $f = $fields[$k];
                $val = $v;
                if ($f['kind'] === 'boolean') {
                    $val = in_array(strtolower($v), ['true', 'yes', 'ja', '1'], true) ? true : (in_array(strtolower($v), ['false', 'no', 'nein', '0'], true) ? false : $v);
                }
                $c = self::coerce($f, $val, $k, $errors, $warnings);
                if ($c !== null) {
                    $specs[$k] = $c;
                }
            } else {
                $specs[$k] = $v;
            }
        }
        if ($errors) {
            throw new UserError('Specs: ' . implode('; ', $errors));
        }
        return $specs;
    }

    public static function specLines(?string $json): string
    {
        $out = [];
        foreach (json_decode((string)$json, true) ?: [] as $k => $v) {
            $out[] = $k . ': ' . (is_bool($v) ? ($v ? 'true' : 'false') : (string)$v);
        }
        return implode("\n", $out);
    }

    public static function save(int $uid, ?int $id, array $f): int
    {
        if (!Catalog::type($f['component_type'])) {
            throw new UserError('Pick a part type.');
        }
        if ($f['model'] === '') {
            throw new UserError('Please enter the model.');
        }
        $dup = Inventory::findProduct($uid, $f['component_type'], $f['maker'], $f['model']);
        if ($dup && (int)$dup['id'] !== $id) {
            throw new UserError('This product exists already.');
        }
        $row = ['component_type' => $f['component_type'], 'maker' => nullable($f['maker']), 'model' => mb_substr($f['model'], 0, 200),
            'list_price_cents' => $f['list_price_cents'], 'notes' => nullable($f['notes']), 'spec_source' => nullable(mb_substr($f['spec_source'], 0, 500)),
            'specs_json' => $f['specs'] ? json_encode($f['specs'], JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION) : null];
        if ($id) {
            $old = self::get($uid, $id);
            if ($old['component_type'] !== $f['component_type'] && (int)Db::value('SELECT COUNT(*) FROM components WHERE product_id = ? AND user_id = ?', [$id, $uid])) {
                throw new UserError('Parts use this product, so its part type stays.');
            }
            if ($row['specs_json'] !== $old['specs_json']) {
                $row['spec_version'] = 'edited ' . today();
            }
            Db::updateOwned('products', $id, $uid, $row);
            return $id;
        }
        return Db::insert('products', $row + ['user_id' => $uid, 'spec_version' => 'typed in ' . today(), 'created_at' => now_utc()]);
    }

    // ------------------------------------------------------------------ instructions for a scraper / agent

    public static function instructions(): string
    {
        $types = [];
        $sections = [];
        foreach (Catalog::types() as $code => $t) {
            $types[] = "| `$code` | {$t['name']} | {$t['category']} |";
            $rows = [];
            foreach (self::specFields($code) as $f) {
                $kind = $f['values'] ? 'one of ' . implode(', ', array_map(fn($v) => "`$v`", $f['values'])) : $f['kind'];
                $rows[] = "| `{$f['key']}` | $kind | " . ($f['unit'] ?? '') . " | {$f['description']} |";
            }
            $lc = strtolower($code);
            $sections[] = "### {$t['name']} (`$code`)\n\nTemplate: `$lc.schema.json`, example: `$lc.example.json`\n\n| key | type | unit | meaning |\n|---|---|---|---|\n" . implode("\n", $rows);
        }
        $ex = rtrim(self::json(self::example('CASSETTE')));
        $F = self::FORMAT;
        $L = self::LIST_FORMAT;
        $M = self::MAX_PRODUCTS;
        $typesTxt = implode("\n", $types);
        $secTxt = implode("\n\n", $sections);
        return <<<MD
# Instructions: write a script that creates Bike Log product files

This document is self-contained. Give it to a developer or an AI coding agent together with the task,
for example: "Write a Python script that reads the product pages I give it and writes Bike Log import
files following these instructions."

Generated by Bike Log (web version) from its import templates (format `$F`). The desktop app reads
the same files.

## What Bike Log does with the files

Bike Log tracks bike parts. It imports **products** (a model you can buy, such as a Shimano CN-M8100
chain) with their specs, and optionally **items** (physical parts the user owns, added as spares).
Import is safe to repeat: the same file twice changes nothing; a changed file updates the product.
A file with any error is rejected as a whole and every error is listed.

## Output files

- UTF-8 JSON, one product per file (recommended) or several in one file:
  `{"format": "$L", "products": [ ... ]}` (a plain JSON list also works).
- File name (recommended): `<component_type in lower case>--<maker>-<model>.json`, using only
  `a-z 0-9 - .`, for example `cassette--shimano-cs-r8100-12-11-34.json`.
- At most $M products per file and 5 MB per file.

## Fields of one product

| field | required | type | rules |
|---|---|---|---|
| `format` | recommended | text | always `"$F"` |
| `component_type` | yes | text | exactly one code from the table below |
| `maker` | yes | text | brand as printed by the maker, e.g. `"Shimano"` |
| `model` | yes | text | model name/number **including the variant that changes what you buy**: size, length, teeth, range. E.g. `"CS-R8100-12 11-34"`, `"RT-CL800 160 mm"`, `"GP5000 S TR 700x28c"` |
| `list_price` | no | number | reference price in **euro**, decimal point, no currency sign, e.g. `69.95` |
| `currency` | no | text | only `"EUR"`; convert other currencies before writing, or leave the price out |
| `specs` | no | object | spec fields of that type (tables below); see rules |
| `source` | strongly recommended | object | `url` (product page), `retrieved_at` (date `YYYY-MM-DD`), `tool` (script name and version) |
| `verified` | no | true/false | always `false` for scraped data; only a person checking the maker's documentation sets `true` |
| `notes` | no | text | anything that does not fit a spec field |
| `items` | no | list | only for parts the user actually owns; a scraper normally leaves this out |

Item fields: `label` (required, unique name such as `"Spare chain 2"`), `price` (euro paid),
`purchase_date` (`YYYY-MM-DD`), `prior_usage` (`"NEW"` or `"UNKNOWN"`), `serial_number`,
`storage_location`, `notes`.

Product identity is `component_type + maker + model` (case-insensitive). Keep `maker` and `model`
spelled the same on every run, otherwise a second product is created. Any other top-level field is an
error; put extra data under `specs`.

## Rules for specs

1. **Never guess.** Leave a field out when the page does not state it. Missing is fine; wrong is not.
2. **Use the units in the tables** and write plain JSON numbers: `"diameter_mm": 160`, not `"160mm"`.
   Convert inches to mm (× 25.4) and pounds to grams (× 453.6) before writing.
3. Whole numbers for `integer` fields (`speeds`, `teeth`, `links`). Decimal point, not comma.
4. `true` / `false` for yes/no fields, without quotes.
5. For "one of" fields use exactly one of the listed values.
6. Spec keys that are not in the table are allowed (text, number or true/false only) and are kept; the
   import reports them as warnings. Use lower_snake_case keys with a unit suffix, e.g. `stack_mm`.
7. Bike Log reads `"12"` or `"1,5"` as numbers but warns; better to write real numbers.

## Part types

| code | name | group |
|---|---|---|
$typesTxt

## Spec fields per type

$secTxt

## Check and import

- In Bike Log: **Parts → Products → Import JSON** → choose files → **Check files** (shows every error
  and what would change) → **Import**.
- Error messages name the place, e.g. `products[2].specs.speeds: expected a whole number, got 11.5`.
- The script can validate before writing with the JSON schemas (download them on the same page;
  JSON Schema draft 2020-12; Python: `jsonschema.validate(doc, schema)`).

## Being a good citizen

Fetch only pages the user asks for, respect the site's robots.txt and terms, wait at least one second
between requests, send an honest User-Agent, never log in or bypass paywalls or bot protection, and keep
the data for the user's own use.

## Complete example

```json
$ex
```

MD;
    }
}
