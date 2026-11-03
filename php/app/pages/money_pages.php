<?php
declare(strict_types=1);

// Bike costs, purchase bundles, sending parts away for repair, part life report.

function page_costs(): void
{
    $uid = (int)require_user()['id'];
    $bike = Domain::bike($uid, get_int('bike'));
    $costs = Costs::bike($uid, (int)$bike['id']);
    $bundles = array_values(array_filter(Bundles::rows($uid), fn($b) => $b['bike_id'] === (int)$bike['id']));
    View::render('money/costs', compact('bike', 'costs', 'bundles'), t('Costs of {bike}', ['bike' => $bike['name']]), 'bikes');
}

function page_bundles(): void
{
    $uid = (int)require_user()['id'];
    $bundles = Bundles::rows($uid, get_param('show') === 'all');
    $candidates = Bundles::candidates($uid);
    View::render('money/bundles', compact('bundles', 'candidates') + ['show' => get_param('show')], t('Bought together'), 'parts');
}

function page_bundle_do(): void
{
    $uid = (int)require_user()['id'];
    if (Request::isPost()) {
        match (post('do')) {
            'create' => Bundles::create($uid, post('name'), array_map('intval', post_list('parts')), nullable(post('merchant')), parse_date(post('purchased_on')),
                parse_money_cents(post('price'), t('Price')), nullable(post('notes'))),
            'add' => Bundles::addMembers($uid, (int)post('id'), array_map('intval', post_list('parts'))),
            'remove' => Bundles::removeMember($uid, (int)post('id'), (int)post('part')),
            'void' => Bundles::void($uid, (int)post('id'), post('reason')),
            default => throw new UserError(t('Unknown action.')),
        };
        Session::flash('ok', t('Saved.'));
    }
    redirect('bundles');
}

function page_repair_send(): void
{
    $uid = (int)require_user()['id'];
    $c = Domain::component($uid, get_int('id'));
    if (Request::isPost()) {
        $g = post('incident');
        ServiceOrders::send($uid, (int)$c['id'], parse_date(post('on'), true), nullable(post('shop')), nullable(post('reason')),
            preg_match('/^[0-9a-f]{32}$/', $g) ? $g : null);
        Session::flash('ok', t('Sent away. It is off the bike and counts no km until it is back.'));
    }
    redirect('part', ['id' => $c['id']]);
}

function page_repair_back(): void
{
    $uid = (int)require_user()['id'];
    $o = ServiceOrders::get($uid, get_int('id'));
    if (Request::isPost()) {
        $r = ServiceOrders::back($uid, (int)$o['id'], parse_date(post('on'), true), post('outcome'), parse_money_cents(post('cost'), t('Cost')),
            nullable(post('receipt')), nullable(post('notes')), post('put_back') === '1', post('keep_as', 'STORED'),
            nullable(post('new_label')), nullable(post('new_serial')), parse_date(post('new_warranty')));
        Session::flash('ok', t('Saved') . ($r['placed'] ? ': ' . $r['placed'] : '') . ($r['incident_solved'] ? t('. The incident is solved.') : '.'));
        redirect('part', ['id' => $r['replacement_id'] ?? $o['component_id']]);
    }
    redirect('part', ['id' => $o['component_id']]);
}

function page_repairs(): void
{
    $uid = (int)require_user()['id'];
    View::render('money/repairs', ['away' => ServiceOrders::rows($uid, ['out' => 1]), 'all' => ServiceOrders::rows($uid)], t('Away for repair'), 'parts');
}

function page_part_life(): void
{
    $uid = (int)require_user()['id'];
    $type = get_param('type');
    View::render('money/part_life', ['types' => PartLife::report($uid, Catalog::type($type) ? $type : null), 'type' => $type], t('Part life'), 'parts');
}
