<?php
declare(strict_types=1);

// Replace a part, wheels into a wheelset, brake overview, restore a maintenance entry.

function page_part_replace(): void
{
    $uid = (int)require_user()['id'];
    $id = get_int('id');
    if (Request::isPost()) {
        $source = post('source');
        $res = Workshop::replace($uid, $id, parse_date(post('on'), true), $source, [
            'label' => post('new_label'), 'price_cents' => parse_money_cents(post('price')), 'purchase_date' => parse_date(post('purchase_date')),
            'prior_usage' => post('prior') === 'UNKNOWN' ? 'UNKNOWN' : 'NEW', 'product_id' => (int)post('product_id') ?: null, 'shop' => nullable(post('shop')),
        ], post('outcome'), array_map('intval', post_list('carry')), nullable(post('reason')));
        Session::flash('ok', 'Replaced: ' . $res['label'] . ' is on now. The old part is ' . mb_strtolower(Inventory::dispositions()[$res['outcome']] ?? $res['outcome']) . '.'
            . ($res['carried'] ? ' ' . $res['carried'] . ' mounted part(s) moved over.' : '')
            . ($res['left_on_old'] ? ' Stayed on the old part (the new one already has that position): ' . implode(', ', $res['left_on_old']) . '.' : '')
            . ' Wrong? Undo it under Spares → Recent steps.');
        redirect('part', ['id' => $res['new_component_id']]);
    }
    $o = Workshop::replaceOptions($uid, $id);
    $products = Db::all('SELECT id, maker, model FROM products WHERE user_id = ? AND component_type = ? ORDER BY maker, model', [$uid, $o['component']['component_type']]);
    View::render('parts/replace', $o + ['products' => $products], 'Replace ' . Domain::componentName($o['component']), 'parts');
}

function page_group_wheels(): void
{
    $uid = (int)require_user()['id'];
    $bike = Domain::bike($uid, get_int('bike'));
    if (Request::isPost()) {
        $res = Workshop::groupWheels($uid, (int)$bike['id'], parse_date(post('on'), true), nullable(post('label')), (int)post('wheelset_id') ?: null);
        Session::flash('ok', 'The wheels are in a wheelset now. From ' . post('on') . ' the wheelset counts km too; the wheels keep their own km.');
        redirect('part', ['id' => $res['wheelset_id']]);
    }
    View::render('bikes/group_wheels', ['bike' => $bike, 'wheels' => Workshop::looseWheels($uid, (int)$bike['id']),
        'choices' => Workshop::wheelsetChoices($uid, (int)$bike['id'])], 'Put wheels into a wheelset', 'bikes');
}

function page_brakes(): void
{
    $uid = (int)require_user()['id'];
    $bikeId = get_int('bike') ?: null;
    $bikes = Db::all("SELECT id, name FROM bikes WHERE user_id = ? AND status = 'ACTIVE' ORDER BY name", [$uid]);
    View::render('maintenance/brakes', ['rows' => Workshop::brakeOverview($uid, $bikeId), 'bikes' => $bikes, 'bikeId' => $bikeId], 'Brakes', 'maintenance');
}

function page_event_restore(): void
{
    $uid = (int)require_user()['id'];
    $e = Db::one('SELECT * FROM maintenance_events WHERE id = ? AND user_id = ?', [get_int('id'), $uid]) ?? throw new NotFound('Entry not found.');
    if (Request::isPost()) {
        Domain::restoreMaintenance($uid, (int)$e['id']);
        Session::flash('ok', 'Entry restored. It counts again for reminders and stock.');
    }
    redirect($e['component_id'] ? 'part' : 'bike', ['id' => $e['component_id'] ?: $e['bike_id']]);
}
