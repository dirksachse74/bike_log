<?php
declare(strict_types=1);

// Products, JSON product import and templates, shop list, change log.

function page_products(): void
{
    $uid = (int)require_user()['id'];
    $type = get_param('type');
    $type = Catalog::type($type) ? $type : '';
    View::render('products/list', ['products' => Products::rows($uid, $type), 'type' => $type], t('Products'), 'parts');
}

function page_product(): void
{
    $uid = (int)require_user()['id'];
    $p = Products::get($uid, get_int('id'));
    if (Request::isPost() && post('do') === 'spare') {
        $label = post('label');
        if ($label === '') {
            throw new UserError(t('Please name the part, e.g. “Spare chain 2”.'));
        }
        $cid = Inventory::createComponent($uid, ['component_type' => $p['component_type'], 'label' => $label, 'product_id' => (int)$p['id'],
            'maker' => $p['maker'], 'model' => $p['model'], 'prior_usage' => post('prior') === 'UNKNOWN' ? 'UNKNOWN' : 'NEW',
            'price_cents' => parse_money_cents(post('price')), 'purchase_date' => parse_date(post('purchase_date')), 'shop' => nullable(post('shop')),
            'storage_location' => nullable(mb_substr(post('storage_location'), 0, 160))]);
        Session::flash('ok', t('Added as a spare.'));
        redirect('part', ['id' => $cid]);
    }
    if (Request::isPost() && post('do') === 'fit') {
        Workshop::setFit($uid, (int)$p['id'], (int)post('bike_id'), post('verified') === '1', nullable(post('note')));
        Session::flash('ok', t('Saved. The Replace form shows this when you change a part on that bike.'));
        redirect('product', ['id' => $p['id']]);
    }
    if (Request::isPost() && post('do') === 'unfit') {
        Workshop::removeFit($uid, (int)$p['id'], (int)post('bike_id'));
        Session::flash('ok', t('Removed.'));
        redirect('product', ['id' => $p['id']]);
    }
    $fits = Workshop::fits($uid, (int)$p['id']);
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    $fields = [];
    foreach (Products::specFields($p['component_type']) as $f) {
        $fields[$f['key']] = $f;
    }
    $parts = Db::all('SELECT * FROM components WHERE user_id = ? AND product_id = ? ORDER BY status, label', [$uid, $p['id']]);
    foreach ($parts as &$c) {
        $c['bike'] = Domain::currentBike($uid, (int)$c['id']);
    }
    unset($c);
    $specs = json_decode((string)$p['specs_json'], true) ?: [];
    View::render('products/show', compact('p', 'fields', 'parts', 'specs', 'fits', 'bikes'), Products::name($p), 'parts');
}

function page_product_edit(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    $p = $id ? Products::get($uid, $id) : ['component_type' => get_param('type'), 'maker' => '', 'model' => '', 'list_price_cents' => null,
        'notes' => '', 'spec_source' => '', 'specs_json' => null];
    if (Request::isPost()) {
        $type = post('component_type');
        $newId = Products::save($uid, $id ?: null, ['component_type' => $type, 'maker' => post('maker'), 'model' => post('model'),
            'list_price_cents' => parse_money_cents(post('list_price'), t('List price')), 'notes' => post('notes'), 'spec_source' => post('spec_source'),
            'specs' => Catalog::type($type) ? Products::parseSpecLines($type, post('specs')) : []]);
        Session::flash('ok', t('Product saved.'));
        redirect('product', ['id' => $newId]);
    }
    View::render('products/edit', ['p' => $p, 'id' => $id, 'specText' => Products::specLines($p['specs_json'])], $id ? t('Edit product') : t('Add a product'), 'parts');
}

/** Where checked files wait for "Import" (one hour at most). */
function import_dir(): string
{
    $d = rtrim((string)Config::get('storage_dir', __DIR__ . '/../../storage'), '/') . '/imports';
    if (!is_dir($d) && !@mkdir($d, 0700, true)) {
        throw new UserError(t('The server cannot store the files for the check (storage folder not writable).'));
    }
    foreach (glob("$d/*.json") ?: [] as $f) {
        if (filemtime($f) < time() - 3600) {
            @unlink($f);
        }
    }
    return $d;
}

function page_product_import(): void
{
    $uid = (int)require_user()['id'];
    $results = [];
    $done = false;
    if (Request::isPost()) {
        $dir = import_dir();
        if (post('do') === 'import') {
            foreach (post_list('token') as $tok) {
                if (!preg_match('/^[a-f0-9]{32}$/', $tok)) {
                    continue;
                }
                $file = "$dir/u$uid-$tok.json";
                if (!is_file($file)) {
                    throw new UserError(t('The checked files are gone (older than an hour?). Choose them again and check them.'));
                }
                $meta = json_decode((string)file_get_contents("$file.name"), true) ?: ['name' => 'file'];
                try {
                    $report = Products::import($uid, Products::parse((string)file_get_contents($file)));
                } catch (UserError $e) {
                    $report = ['ok' => false, 'errors' => [$e->getMessage()], 'warnings' => [], 'products' => [], 'counts' => []];
                }
                $results[] = ['name' => $meta['name'], 'report' => $report];
                @unlink($file);
                @unlink("$file.name");
            }
            $done = true;
            $n = count(array_filter($results, fn($r) => $r['report']['ok']));
            ChangeLog::note($uid, 'product', null, t('JSON import: {n} of {total} files imported', ['n' => $n, 'total' => count($results)]));
            Session::flash($n === count($results) ? 'ok' : 'error', t('{n} of {total} files imported.', ['n' => $n, 'total' => count($results)]));
        } else {
            $files = $_FILES['files'] ?? null;
            if (!$files || !is_array($files['name'])) {
                throw new UserError(t('Choose one or more JSON files.'));
            }
            if (count($files['name']) > 50) {
                throw new UserError(t('At most 50 files at once.'));
            }
            foreach ($files['name'] as $i => $name) {
                $name = mb_substr(basename((string)$name), 0, 120);
                if ($files['error'][$i] !== UPLOAD_ERR_OK) {
                    $results[] = ['name' => $name, 'report' => ['ok' => false, 'errors' => [$files['error'][$i] === UPLOAD_ERR_NO_FILE ? t('No file chosen.') : t('Upload failed (too large?).')],
                        'warnings' => [], 'products' => [], 'counts' => []]];
                    continue;
                }
                $content = (string)file_get_contents($files['tmp_name'][$i]);
                try {
                    $report = Products::import($uid, Products::parse($content), true);
                } catch (UserError $e) {
                    $report = ['ok' => false, 'errors' => [$e->getMessage()], 'warnings' => [], 'products' => [], 'counts' => []];
                }
                $token = null;
                if ($report['ok']) {
                    $token = bin2hex(random_bytes(16));
                    file_put_contents("$dir/u$uid-$token.json", $content);
                    file_put_contents("$dir/u$uid-$token.json.name", json_encode(['name' => $name]));
                }
                $results[] = ['name' => $name, 'report' => $report, 'token' => $token];
            }
        }
    }
    View::render('products/import', ['results' => $results, 'done' => $done, 'types' => Catalog::typesByCategory()], t('Import products (JSON)'), 'parts');
}

function page_product_template(): void
{
    require_user();
    $kind = get_param('kind');
    if ($kind === 'instructions') {
        header('Content-Type: text/markdown; charset=utf-8');
        header('Content-Disposition: attachment; filename="AGENT_INSTRUCTIONS.md"');
        echo Products::instructions();
        exit;
    }
    $type = get_param('type');
    if (!Catalog::type($type) || !in_array($kind, ['schema', 'example'], true)) {
        throw new NotFound(t('No such template.'));
    }
    header('Content-Type: application/json; charset=utf-8');
    header('Content-Disposition: attachment; filename="' . strtolower($type) . ".$kind.json\"");
    echo Products::json($kind === 'schema' ? Products::schema($type) : Products::example($type));
    exit;
}

// ------------------------------------------------------------------ shop list

function page_lists(): void
{
    $uid = (int)require_user()['id'];
    $code = 'SHOP';
    if (Request::isPost()) {
        $do = post('do');
        $id = get_int('id');
        match ($do) {
            'add' => PickLists::add($uid, $code, post('name')),
            'rename' => Session::flash('ok', t('Renamed; {n} records follow.', ['n' => PickLists::rename($uid, $id, post('name'))])),
            'merge' => Session::flash('ok', t('Merged; {n} records moved.', ['n' => PickLists::merge($uid, $id, (int)post('into'))])),
            'hide' => PickLists::hide($uid, $id, true),
            'show' => PickLists::hide($uid, $id, false),
            default => throw new UserError(t('Unknown action.')),
        };
        redirect('lists');
    }
    $rows = PickLists::rows($uid, $code);
    View::render('products/lists', ['rows' => $rows, 'list' => PickLists::LISTS[$code]], t('Shops'), 'account');
}

// ------------------------------------------------------------------ change log

function page_changes(): void
{
    $uid = (int)require_user()['id'];
    $bikeId = get_int('bike');
    $partId = get_int('part');
    $entity = get_param('entity');
    $entity = isset(ChangeLog::ENTITY_LABELS[$entity]) ? $entity : '';
    $before = get_int('before');
    $rows = ChangeLog::entries($uid, $bikeId ?: null, $partId ?: null, $entity ?: null, 200, $before);
    $bike = $bikeId ? Domain::bike($uid, $bikeId) : null;
    $part = $partId ? Domain::component($uid, $partId) : null;
    View::render('account/changes', compact('rows', 'bike', 'part', 'entity', 'bikeId', 'partId'), t('Change log'), 'account');
}
