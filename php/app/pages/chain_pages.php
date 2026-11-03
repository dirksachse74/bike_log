<?php
declare(strict_types=1);

// Chain rotation of one bike: which chain is on, which are waxed and ready, swap, hot wax, add a chain.

function page_chains(): void
{
    $uid = (int)require_user()['id'];
    $bikeId = get_int('bike');
    if (!$bikeId) {
        $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
        if (count($bikes) === 1) {
            redirect('chains', ['bike' => $bikes[0]['id']]);
        }
        View::render('chains/choose', compact('bikes'), t('Chain rotation'), 'parts');
        return;
    }
    $rot = Chains::rotation($uid, $bikeId);
    $waxes = Db::all("SELECT id, name, unit FROM consumables WHERE user_id = ? AND kind = 'WAX' AND archived_at IS NULL ORDER BY name", [$uid]);
    View::render('chains/rotation', compact('rot', 'waxes'), t('Chains of {bike}', ['bike' => $rot['bike']['name']]), 'parts');
}

function page_chain_do(): void
{
    $uid = (int)require_user()['id'];
    $bikeId = get_int('bike');
    if (Request::isPost()) {
        $on = parse_date(post('on', today()), true);
        $msg = match (post('do')) {
            'swap' => Chains::swap($uid, $bikeId, (int)post('to'), $on),
            'wax' => Chains::wax($uid, $bikeId, array_map('intval', post_list('chains')), $on, (int)post('consumable_id') ?: null,
                parse_number(post('qty'), t('Amount')), (int)post('then_install') ?: null),
            'add' => Chains::add($uid, $bikeId, post('pick'), $on)['text'],
            'leave' => (function () use ($uid) {
                Chains::leave($uid, (int)post('id'));
                return t('Taken out of the rotation (the chain itself stays).');
            })(),
            default => throw new UserError(t('Unknown action.')),
        };
        Session::flash('ok', $msg);
    }
    redirect('chains', ['bike' => $bikeId]);
}
