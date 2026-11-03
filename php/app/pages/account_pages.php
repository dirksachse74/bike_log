<?php
declare(strict_types=1);

// "My account": name, time zone, email, password, sign out everywhere, data export, delete account.

function page_account(): void
{
    $u = require_user();
    $uid = (int)$u['id'];
    if (Request::isPost()) {
        switch (post('do')) {
            case 'profile':
                $name = post('display_name');
                if ($name === '' || mb_strlen($name) > 100) {
                    throw new UserError(t('Please enter your name (up to 100 characters).'));
                }
                $tz = post('timezone');
                if (!in_array($tz, DateTimeZone::listIdentifiers(), true)) {
                    throw new UserError(t('Unknown time zone.'));
                }
                Db::run('UPDATE users SET display_name = ?, timezone = ?, updated_at = ? WHERE id = ?', [$name, $tz, now_utc(), $uid]);
                Session::flash('ok', t('Saved.'));
                break;
            case 'password':
                if (post('password') !== post('password2')) {
                    throw new UserError(t('The two new passwords are not the same.'));
                }
                Auth::changePassword($uid, post('current'), post('password'));
                Mailer::send($u['email'], t('Your password was changed'), t("Hello,\n\nthe password of your {site} account was just changed. Other browsers were signed out.\nIf this was not you, reset it now: {link}\n",
                    ['site' => Settings::get('site_name'), 'link' => abs_url('forgot')]));
                Session::flash('ok', t('Password changed. Other browsers and devices are signed out.'));
                break;
            case 'email':
                if (!password_verify(post('current'), $u['password_hash'])) {
                    throw new UserError(t('Your password is wrong.'));
                }
                $new = Auth::normalizeEmail(post('email'));
                if (!filter_var($new, FILTER_VALIDATE_EMAIL)) {
                    throw new UserError(t('Please enter a valid email address.'));
                }
                if ($new === $u['email']) {
                    throw new UserError(t('That is already your address.'));
                }
                if (!RateLimit::allowed('email-change', (string)$uid, 3, 3600)) {
                    throw new UserError(t('Too many attempts. Please wait an hour.'));
                }
                RateLimit::hit('email-change', (string)$uid);
                if (!Db::one('SELECT id FROM users WHERE email = ?', [$new])) {
                    $t = Auth::createToken($uid, 'EMAIL_CHANGE', 86400, $new);
                    Mailer::send($new, t('Confirm your new email address'), t("Hello,\n\nplease confirm this address for your {site} account:\n\n{link}\n\nThe link works once and expires in 24 hours.\n",
                        ['site' => Settings::get('site_name'), 'link' => abs_url('confirm_email', ['t' => $t])]));
                }
                Audit::log('email_change_requested', $uid, $new);
                Session::flash('ok', t('We sent a link to {email}. Your address changes when you open it.', ['email' => $new]));
                break;
            case 'logout_all':
                Auth::bumpSessions($uid);
                Audit::log('logout_everywhere', $uid);
                Auth::logoutLocal();
                Session::flash('ok', t('You are signed out on all devices.'));
                redirect('login');
            case 'delete':
                if (!password_verify(post('current'), $u['password_hash'])) {
                    throw new UserError(t('Your password is wrong.'));
                }
                if (post('confirm') !== 'DELETE') {
                    throw new UserError(t('Type DELETE to confirm.'));
                }
                if ($u['role'] === 'ADMIN' && (int)Db::value("SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND status = 'ACTIVE'") <= 1) {
                    throw new UserError(t('You are the only admin. Make someone else admin first.'));
                }
                Audit::log('account_deleted', null, 'self, user #' . $uid);
                Db::run('DELETE FROM users WHERE id = ?', [$uid]);
                Auth::logoutLocal();
                Session::flash('ok', t('Your account and all its data are deleted.'));
                redirect('login');
        }
        redirect('account');
    }
    View::render('account/show', ['u' => $u], t('My account'), 'account');
}

/** Everything the user owns as one JSON file. */
function export_user_data(int $uid): array
{
    return UserBackups::export($uid);
}

function page_export(): void
{
    $u = require_user();
    if (!Request::isPost()) {
        redirect('account');
    }
    Audit::log('data_exported', (int)$u['id']);
    header('Content-Type: application/json; charset=utf-8');
    header('Content-Disposition: attachment; filename="bikelog-export-' . today() . '.json"');
    echo UserBackups::encode(export_user_data((int)$u['id']));
    exit;
}
