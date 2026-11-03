<?php
declare(strict_types=1);

// Backups, restore, fresh start, diagnostics (all for the signed-in user's own data).

function page_backups(): void
{
    $u = require_user();
    $uid = (int)$u['id'];
    if (Request::isPost()) {
        $do = post('do');
        if ($do === 'save') {
            UserBackups::save($uid, 'MANUAL');
            Session::flash('ok', t('Copy stored. It is listed below.'));
            redirect('backups');
        }
        if ($do === 'download') {
            $json = UserBackups::content($uid, get_int('id'));
            Audit::log('data_exported', $uid, 'stored copy ' . get_int('id'));
            header('Content-Type: application/json; charset=utf-8');
            header('Content-Disposition: attachment; filename="bikelog-backup-' . get_int('id') . '.json"');
            echo $json;
            exit;
        }
        if (post('confirm') !== UserBackups::CONFIRM_RESTORE) {
            throw new UserError(t('Type {word} to confirm. Restoring replaces all your current data.', ['word' => UserBackups::CONFIRM_RESTORE]));
        }
        if ($do === 'restore') {
            $id = get_int('id');
            $b = Db::one('SELECT created_at FROM user_backups WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound(t('Backup not found.'));
            $res = UserBackups::restore($uid, UserBackups::parse(UserBackups::content($uid, $id)), t('the copy of {when}', ['when' => local_time($b['created_at'])]));
        } elseif ($do === 'upload') {
            $f = $_FILES['file'] ?? null;
            if (!$f || !is_string($f['tmp_name'] ?? null) || $f['error'] !== UPLOAD_ERR_OK) {
                throw new UserError(t('Choose the file you downloaded (Account → Download all my data).'));
            }
            if ($f['size'] > UserBackups::MAX_UPLOAD) {
                throw new UserError(t('The file is larger than 20 MB.'));
            }
            $res = UserBackups::restore($uid, UserBackups::parse((string)file_get_contents($f['tmp_name'])), t('the file {name}', ['name' => mb_substr(basename((string)$f['name']), 0, 80)]));
        } else {
            throw new UserError(t('Unknown action.'));
        }
        Audit::log('data_restored', $uid, $res['summary']);
        Session::flash('ok', t('Restored: {summary}. Your data from before is stored as a copy below.', ['summary' => $res['summary']])
            . ($res['warnings'] ? ' ' . t('Note: {list}', ['list' => implode('; ', $res['warnings'])]) : ''));
        redirect('backups');
    }
    View::render('account/backups', ['rows' => UserBackups::rows($uid)], t('Backups'), 'account');
}

function page_fresh_start(): void
{
    $u = require_user();
    $uid = (int)$u['id'];
    if (Request::isPost()) {
        if (post('confirm') !== UserBackups::CONFIRM_RESET) {
            throw new UserError(t('Type {word} to confirm.', ['word' => UserBackups::CONFIRM_RESET]));
        }
        if (!password_verify(post('current'), (string)$u['password_hash'])) {
            throw new UserError(t('That is not your password.'));
        }
        UserBackups::freshStart($uid);
        Audit::log('fresh_start', $uid);
        Session::flash('ok', t('Fresh start done. Your old data is stored under Backups; restore it there if you change your mind.'));
        redirect('home');
    }
    $counts = [];
    foreach (['bikes' => t('bikes'), 'components' => t('parts'), 'rides' => t('rides'), 'maintenance_events' => t('maintenance entries')] as $t => $label) {
        $counts[$label] = (int)Db::value("SELECT COUNT(*) FROM $t WHERE user_id = ?", [$uid]);
    }
    View::render('account/fresh_start', ['counts' => $counts], t('Fresh start'), 'account');
}

function page_diagnostics(): void
{
    $u = require_user();
    $uid = (int)$u['id'];
    $counts = [];
    foreach (array_keys(UserBackups::TABLES) as $t) {
        $counts[$t] = (int)Db::value("SELECT COUNT(*) FROM $t WHERE user_id = ?", [$uid]);
    }
    $applied = Migrator::applied();
    $checks = [
        'Rides without a distance (not in the km)' => (int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ? AND removed_at IS NULL AND distance_km IS NULL', [$uid]),
        'Rides without a bike' => (int)Db::value('SELECT COUNT(*) FROM rides WHERE user_id = ? AND removed_at IS NULL AND bike_id IS NULL', [$uid]),
        'Parts fitted twice at the same time' => (int)Db::value('SELECT COUNT(*) FROM (SELECT component_id FROM installations WHERE user_id = ? AND voided_at IS NULL
            AND removed_on IS NULL GROUP BY component_id HAVING COUNT(*) > 1) x', [$uid]),
        'Two parts in one position' => (int)Db::value('SELECT COUNT(*) FROM (SELECT 1 FROM installations WHERE user_id = ? AND voided_at IS NULL AND removed_on IS NULL
            GROUP BY COALESCE(bike_id, 0), COALESCE(parent_component_id, 0), slot HAVING COUNT(*) > 1) x', [$uid]),
        'Parts on a retired bike' => (int)Db::value("SELECT COUNT(*) FROM installations i JOIN bikes b ON b.id = i.bike_id WHERE i.user_id = ? AND i.voided_at IS NULL
            AND i.removed_on IS NULL AND b.status <> 'ACTIVE'", [$uid]),
    ];
    View::render('account/diagnostics', ['counts' => $counts, 'applied' => $applied, 'pending' => array_keys(Migrator::pending()), 'checks' => $checks,
        'php' => PHP_VERSION, 'db' => (string)Db::value('SELECT VERSION()')], t('Diagnostics'), 'account');
}
