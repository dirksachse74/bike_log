<?php
declare(strict_types=1);

// One ride with its incidents, the incident list, fixes, punctures, broken spokes and the journal.

function page_ride(): void
{
    $uid = (int)require_user()['id'];
    $ride = Incidents::ride($uid, get_int('id'));
    $bike = $ride['bike_id'] ? Domain::bike($uid, (int)$ride['bike_id']) : null;
    $type = get_param('type');
    $choices = $type !== '' && isset(Incidents::types()[$type]) ? Incidents::choices($uid, $ride, $type) : [];
    $incidents = Incidents::list($uid, ['ride_id' => $ride['id']]);
    View::render('rides/show', compact('ride', 'bike', 'type', 'choices', 'incidents') + ['fixData' => fix_data($uid, $incidents)],
        ($ride['name'] ?: 'Ride') . ' · ' . $ride['ride_date'], 'rides');
}

function page_incident_log(): void
{
    $uid = (int)require_user()['id'];
    $rideId = get_int('ride');
    if (Request::isPost()) {
        $solved = post('solved') === '1' ? parse_date(post('solved_on') ?: Incidents::ride($uid, $rideId)['ride_date'], true) : null;
        Incidents::log($uid, $rideId, post('type'), post_list('affected'), nullable(post('text')), $solved);
        Session::flash('ok', 'Incident logged. Say what you did about it below, per part.');
    }
    redirect('ride', ['id' => $rideId]);
}

function page_incidents(): void
{
    $uid = (int)require_user()['id'];
    $show = get_param('show', 'open');
    $f = $show === 'open' ? ['open' => 1] : ($show === 'removed' ? ['removed' => 1] : []);
    if (get_int('bike')) {
        $f['bike_id'] = get_int('bike');
    }
    $incidents = Incidents::list($uid, $f);
    View::render('incidents/list', ['incidents' => $incidents, 'show' => $show, 'fixData' => fix_data($uid, $incidents)], 'Incidents', 'rides');
}

function page_incident(): void
{
    $uid = (int)require_user()['id'];
    $group = post('group');
    if (Request::isPost() && preg_match('/^[0-9a-f]{32}$/', $group)) {
        match (post('do')) {
            'solve' => Incidents::setSolved($uid, $group, parse_date(post('on', today()), true)),
            'reopen' => Incidents::setSolved($uid, $group, null),
            'remove' => Incidents::remove($uid, $group),
            'restore' => Incidents::restore($uid, $group),
            default => throw new UserError('Unknown action.'),
        };
        Session::flash('ok', ['solve' => 'Marked as solved.', 'reopen' => 'Open again.', 'remove' => 'Incident removed. You can restore it from "Removed".',
            'restore' => 'Incident restored.'][post('do')]);
    }
    back_to(post('back'));
}

function page_incident_fix(): void
{
    $uid = (int)require_user()['id'];
    if (Request::isPost()) {
        $entry = (int)post('entry');
        if (post('do') === 'undo') {
            Incidents::undoFix($uid, $entry);
            Session::flash('ok', 'Fix undone; parts and stock are back as before.');
        } else {
            $src = [];
            $s = post('source', 'new');
            if (preg_match('/^(spare|stock):(\d+)$/', $s, $m)) {
                $src = ['kind' => $m[1], 'id' => (int)$m[2]];
            } else {
                $src = ['kind' => 'new', 'label' => post('new_label')];
            }
            if (post('outcome') !== '') {
                $src['outcome'] = isset(Inventory::dispositions()[post('outcome')]) ? post('outcome') : throw new UserError('Unknown choice for the old part.');
            }
            Incidents::fix($uid, $entry, post('action'), parse_date(post('on'), true), $src, nullable(post('text')));
            Session::flash('ok', 'Fix saved.');
        }
    }
    back_to(post('back'));
}

/** Choices for the fix forms: per affected entry, where a replacement can come from. */
function fix_data(int $uid, array $incidents): array
{
    $out = [];
    $stock = Db::all("SELECT * FROM consumables WHERE user_id = ? AND tracking_mode = 'COUNTED' AND archived_at IS NULL", [$uid]);
    foreach ($incidents as $inc) {
        foreach ($inc['affected'] as $a) {
            $type = $a['component_type'] ?? null;
            if ($inc['type'] === 'SPOKE') {
                $type = 'SPOKES';
            } elseif (!$type && $a['affected']) {
                $type = str_contains(mb_strtolower($a['affected']), 'tube') ? 'INNER_TUBE' : (str_contains(mb_strtolower($a['affected']), 'tire') ? 'TIRE' : null);
            }
            $src = [];
            if ($type) {
                if ($a['component_id'] && $inc['type'] !== 'SPOKE') {
                    $src['new'] = 'A new ' . mb_strtolower(Catalog::typeName($type)) . ' (not in my records yet)';
                    foreach (Inventory::individualSpares($uid, $type) as $s) {
                        $src['spare:' . $s['id']] = 'Spare: ' . Domain::componentName($s);
                    }
                } else {
                    $src['new'] = 'Not tracked';
                }
                foreach ($stock as $l) {
                    if ($l['component_type'] === $type) {
                        $src['stock:' . $l['id']] = 'From stock: ' . $l['name'] . ' (' . fmt_qty(Inventory::stockLevel($uid, (int)$l['id'])) . ' left)';
                    }
                }
            }
            $out[$a['id']] = ['sources' => $src, 'replaceable' => (bool)$type || (bool)$a['component_id'],
                'old_part' => $a['component_id'] && $inc['type'] !== 'SPOKE',
                'default_outcome' => $type ? Inventory::defaultOutcome($type) : 'STORED'];
        }
    }
    return $out;
}

/** Redirect to a page inside the app named by a "back" field (route + params), never elsewhere. */
function back_to(string $back): never
{
    parse_str($back, $q);
    $r = is_string($q['r'] ?? null) ? $q['r'] : 'home';
    if (!isset(Routes::all()[$r])) {
        $r = 'home';
    }
    unset($q['r']);
    $params = [];
    foreach ($q as $k => $v) {
        if (is_string($k) && is_string($v) && preg_match('/^[a-z_]+$/', $k) && preg_match('/^[\w-]*$/', $v)) {
            $params[$k] = $v;
        }
    }
    redirect($r, $params);
}

function page_punctures(): void
{
    $uid = (int)require_user()['id'];
    View::render('incidents/punctures', ['p' => Incidents::punctures($uid)], 'Punctures', 'rides');
}

function page_spoke(): void
{
    $uid = (int)require_user()['id'];
    $wheel = Domain::component($uid, get_int('id'));
    if (Request::isPost()) {
        $replaced = post('replaced') === '1' ? parse_date(post('replaced_on') ?: post('broke_on'), true) : null;
        $stock = preg_match('/^stock:(\d+)$/', post('source'), $m) ? (int)$m[1] : null;
        Incidents::logSpoke($uid, (int)$wheel['id'], parse_date(post('broke_on'), true), nullable(post('note')), $replaced, $stock);
        Session::flash('ok', 'Broken spoke logged' . ($replaced ? ' and replaced.' : '. Log the new spoke when it is in.'));
    }
    redirect('part', ['id' => $wheel['id']]);
}

function page_journal(): void
{
    $uid = (int)require_user()['id'];
    if (Request::isPost()) {
        $do = post('do');
        if ($do === 'add') {
            $bikeId = (int)post('bike_id') ?: null;
            $cid = (int)post('component_id') ?: null;
            if ($bikeId) {
                Domain::bike($uid, $bikeId);
            }
            if ($cid) {
                Domain::component($uid, $cid);
                $bikeId = $bikeId ?? (Domain::currentBike($uid, $cid)['id'] ?? null);
            }
            if (mb_strlen(post('text')) > 5000) {
                throw new UserError('That note is too long (5000 characters at most).');
            }
            Journal::add($uid, ['bike_id' => $bikeId, 'component_id' => $cid, 'entry_on' => parse_date(post('entry_on'), true),
                'kind' => post('kind') === 'ISSUE' ? 'ISSUE' : 'NOTE', 'text' => post('text')]);
            Session::flash('ok', 'Saved.');
        } else {
            $e = Db::one('SELECT * FROM journal_entries WHERE id = ? AND user_id = ? AND incident_group IS NULL', [(int)post('id'), $uid])
                ?? throw new NotFound('Entry not found.');
            $row = match ($do) {
                'void' => ['voided_at' => now_utc(), 'void_reason' => post('reason') ?: 'removed'],
                'restore' => ['voided_at' => null, 'void_reason' => null],
                'resolve' => ['resolved_on' => parse_date(post('on', today()), true)],
                'reopen' => ['resolved_on' => null],
                default => throw new UserError('Unknown action.'),
            };
            Db::updateOwned('journal_entries', (int)$e['id'], $uid, $row + ['updated_at' => now_utc()]);
            Session::flash('ok', 'Saved.');
        }
    }
    back_to(post('back'));
}
