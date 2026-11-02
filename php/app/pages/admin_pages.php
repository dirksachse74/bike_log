<?php
declare(strict_types=1);

// Admin area. Admins manage accounts, invitations, site settings, database updates and backups.
// Privacy: admins see counts of a user's records, never the bikes, rides or notes themselves.

function page_admin(): void
{
    require_admin();
    $stats = Db::one("SELECT COUNT(*) users, SUM(status = 'BLOCKED') blocked, SUM(email_verified_at IS NULL) unverified,
        SUM(last_login_at > ?) active30, SUM(role = 'ADMIN') admins FROM users", [gmdate('Y-m-d H:i:s', time() - 86400 * 30)]);
    $data = Db::one('SELECT (SELECT COUNT(*) FROM bikes) bikes, (SELECT COUNT(*) FROM components) parts, (SELECT COUNT(*) FROM rides) rides,
        (SELECT COUNT(*) FROM maintenance_events) events');
    $failed24 = (int)Db::value("SELECT COUNT(*) FROM audit_log WHERE event IN ('login_failed','login_throttled') AND created_at > ?", [gmdate('Y-m-d H:i:s', time() - 86400)]);
    $recent = Db::all('SELECT a.*, u.email AS subject_email FROM audit_log a LEFT JOIN users u ON u.id = a.subject_user_id ORDER BY a.id DESC LIMIT 10');
    $pending = array_keys(Migrator::pending());
    $sys = ['php' => PHP_VERSION, 'db' => (string)Db::value('SELECT VERSION()'), 'app' => BIKELOG_PHP_VERSION,
        'mail' => (string)Config::get('mail.transport'), 'https' => Request::isHttps(), 'argon' => defined('PASSWORD_ARGON2ID')];
    View::render('admin/dashboard', compact('stats', 'data', 'failed24', 'recent', 'pending', 'sys'), 'Admin', 'admin');
}

function page_admin_users(): void
{
    require_admin();
    $q = get_param('q');
    $filter = get_param('filter');
    $sql = 'SELECT u.*, (SELECT COUNT(*) FROM rides r WHERE r.user_id = u.id) rides, (SELECT COUNT(*) FROM bikes b WHERE b.user_id = u.id) bikes FROM users u WHERE 1=1';
    $args = [];
    if ($q !== '') {
        $sql .= ' AND (u.email LIKE ? OR u.display_name LIKE ?)';
        $like = '%' . str_replace(['\\', '%', '_'], ['\\\\', '\\%', '\\_'], $q) . '%';
        $args[] = $like;
        $args[] = $like;
    }
    $sql .= match ($filter) {
        'blocked' => " AND u.status = 'BLOCKED'",
        'unverified' => ' AND u.email_verified_at IS NULL',
        'admins' => " AND u.role = 'ADMIN'",
        default => '',
    };
    $users = Db::all($sql . ' ORDER BY u.created_at DESC LIMIT 500', $args);
    $invites = Db::all("SELECT t.*, u.display_name AS by_name FROM user_tokens t LEFT JOIN users u ON u.id = t.created_by
        WHERE t.purpose = 'INVITE' AND t.used_at IS NULL AND t.expires_at > ? ORDER BY t.id DESC", [now_utc()]);
    View::render('admin/users', compact('users', 'q', 'filter', 'invites'), 'Users', 'admin');
}

function page_admin_user(): void
{
    $me = require_admin();
    $u = Db::one('SELECT * FROM users WHERE id = ?', [get_int('id')]) ?? throw new NotFound('User not found.');
    $uid = (int)$u['id'];
    $self = $uid === (int)$me['id'];
    if (Request::isPost()) {
        $do = post('do');
        $lastAdmin = $u['role'] === 'ADMIN' && (int)Db::value("SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND status = 'ACTIVE'") <= 1;
        if ($self && in_array($do, ['block', 'demote', 'delete'], true)) {
            throw new UserError('You cannot do this to your own account here.');
        }
        switch ($do) {
            case 'block':
                if ($lastAdmin) {
                    throw new UserError('This is the last admin.');
                }
                Db::run("UPDATE users SET status = 'BLOCKED', blocked_reason = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?",
                    [nullable(post('reason')), now_utc(), $uid]);
                Audit::log('admin_block', $uid, post('reason'));
                Session::flash('ok', 'Blocked and signed out everywhere.');
                break;
            case 'unblock':
                Db::run("UPDATE users SET status = 'ACTIVE', blocked_reason = NULL, updated_at = ? WHERE id = ?", [now_utc(), $uid]);
                Audit::log('admin_unblock', $uid);
                Session::flash('ok', 'Unblocked.');
                break;
            case 'verify':
                Db::run('UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?', [now_utc(), now_utc(), $uid]);
                Audit::log('admin_verify_email', $uid);
                Session::flash('ok', 'Email marked as confirmed.');
                break;
            case 'resend_verify':
                Auth::sendVerification($uid, $u['email']);
                Audit::log('admin_resend_verify', $uid);
                Session::flash('ok', 'Confirmation link sent.');
                break;
            case 'send_reset':
                Auth::sendReset($uid, $u['email']);
                Audit::log('admin_send_reset', $uid);
                Session::flash('ok', 'Password reset link sent to ' . $u['email'] . ' (valid 1 hour).');
                break;
            case 'unlock':
                RateLimit::clear('login-email', $u['email']);
                Audit::log('admin_unlock_login', $uid);
                Session::flash('ok', 'Sign-in lock cleared.');
                break;
            case 'logout_all':
                Auth::bumpSessions($uid);
                Audit::log('admin_logout_everywhere', $uid);
                Session::flash('ok', 'Signed out on all devices.');
                break;
            case 'promote':
                Db::run("UPDATE users SET role = 'ADMIN', updated_at = ? WHERE id = ?", [now_utc(), $uid]);
                Audit::log('admin_promote', $uid);
                Session::flash('ok', 'Now an admin.');
                break;
            case 'demote':
                if ($lastAdmin) {
                    throw new UserError('This is the last admin.');
                }
                Db::run("UPDATE users SET role = 'USER', session_version = session_version + 1, updated_at = ? WHERE id = ?", [now_utc(), $uid]);
                Audit::log('admin_demote', $uid);
                Session::flash('ok', 'No longer an admin.');
                break;
            case 'delete':
                if (Auth::normalizeEmail(post('confirm_email')) !== $u['email']) {
                    throw new UserError('Type the user\'s email address to confirm.');
                }
                if ($lastAdmin) {
                    throw new UserError('This is the last admin.');
                }
                Audit::log('admin_delete_user', null, 'user #' . $uid . ' ' . $u['email']);
                Db::run('DELETE FROM users WHERE id = ?', [$uid]);
                Session::flash('ok', 'Account and all its data deleted.');
                redirect('admin_users');
        }
        redirect('admin_user', ['id' => $uid]);
    }
    $counts = Db::one('SELECT (SELECT COUNT(*) FROM bikes WHERE user_id = ?) bikes, (SELECT COUNT(*) FROM components WHERE user_id = ?) parts,
        (SELECT COUNT(*) FROM rides WHERE user_id = ?) rides, (SELECT COUNT(*) FROM maintenance_events WHERE user_id = ?) events',
        [$uid, $uid, $uid, $uid]);
    $audit = Db::all('SELECT * FROM audit_log WHERE subject_user_id = ? OR actor_user_id = ? ORDER BY id DESC LIMIT 30', [$uid, $uid]);
    $locked = !RateLimit::allowed('login-email', $u['email'], 5, 900);
    View::render('admin/user', compact('u', 'counts', 'audit', 'self', 'locked'), $u['display_name'], 'admin');
}

function page_admin_invite(): void
{
    require_admin();
    if (Request::isPost()) {
        if (post('do') === 'revoke') {
            Db::run("UPDATE user_tokens SET used_at = ? WHERE id = ? AND purpose = 'INVITE' AND used_at IS NULL", [now_utc(), (int)post('token_id')]);
            Audit::log('invite_revoked', null, post('token_id'));
            Session::flash('ok', 'Invitation withdrawn.');
        } else {
            Auth::invite(post('email'));
            Session::flash('ok', 'Invitation sent to ' . Auth::normalizeEmail(post('email')) . ' (valid 7 days).');
        }
    }
    redirect('admin_users');
}

function page_admin_audit(): void
{
    require_admin();
    $event = get_param('event');
    $userId = get_int('user');
    $page = max(1, get_int('page'));
    $sql = 'FROM audit_log a LEFT JOIN users s ON s.id = a.subject_user_id LEFT JOIN users ac ON ac.id = a.actor_user_id WHERE 1=1';
    $args = [];
    if ($event !== '') {
        $sql .= ' AND a.event = ?';
        $args[] = $event;
    }
    if ($userId) {
        $sql .= ' AND (a.subject_user_id = ? OR a.actor_user_id = ?)';
        $args[] = $userId;
        $args[] = $userId;
    }
    $per = 100;
    $count = (int)Db::value("SELECT COUNT(*) $sql", $args);
    $rows = Db::all("SELECT a.*, s.email AS subject_email, ac.email AS actor_email $sql ORDER BY a.id DESC LIMIT $per OFFSET " . (($page - 1) * $per), $args);
    $events = Db::run('SELECT DISTINCT event FROM audit_log ORDER BY event')->fetchAll(PDO::FETCH_COLUMN);
    View::render('admin/audit', compact('rows', 'events', 'event', 'userId', 'page', 'count', 'per'), 'Audit log', 'admin');
}

function page_admin_settings(): void
{
    require_admin();
    if (Request::isPost()) {
        $changes = [];
        $vals = [
            'site_name' => mb_substr(post('site_name') ?: 'Bike Log', 0, 60),
            'registration' => in_array(post('registration'), ['open', 'invite', 'closed'], true) ? post('registration') : 'invite',
            'require_verification' => post('require_verification') === '1' ? '1' : '0',
            'allowed_email_domains' => mb_strtolower(preg_replace('/\s+/', '', post('allowed_email_domains'))),
            'maintenance_mode' => post('maintenance_mode') === '1' ? '1' : '0',
            'notice' => mb_substr(post('notice'), 0, 300),
        ];
        foreach ($vals as $k => $v) {
            if (Settings::get($k) !== $v) {
                $changes[] = "$k=" . mb_substr($v, 0, 40);
                Settings::set($k, $v);
            }
        }
        if ($changes) {
            Audit::log('settings_changed', null, implode(', ', $changes));
        }
        Session::flash('ok', 'Settings saved.');
        redirect('admin_settings');
    }
    View::render('admin/settings', [], 'Site settings', 'admin');
}

function page_admin_system(): void
{
    $me = require_admin();
    if (Request::isPost()) {
        switch (post('do')) {
            case 'migrate':
                $done = Migrator::migrate();
                Audit::log('db_migrated', null, implode(',', $done) ?: 'nothing to do');
                Session::flash('ok', $done ? 'Database updated: ' . implode(', ', $done) : 'The database was already up to date.');
                break;
            case 'test_mail':
                $ok = Mailer::send($me['email'], 'Test email from ' . Settings::get('site_name'), "Hello,\n\nthis is a test. Email sending works.\n");
                Audit::log('test_mail', (int)$me['id'], $ok ? 'ok' : 'failed');
                Session::flash($ok ? 'ok' : 'error', $ok ? 'Test email sent to ' . $me['email'] . '. Check your inbox (and spam).'
                    : 'Sending failed. See storage/php-error.log on the server for the reason.');
                break;
            case 'cleanup':
                $a = Db::run('DELETE FROM user_tokens WHERE expires_at < ? OR used_at < ?', [gmdate('Y-m-d H:i:s', time() - 86400), gmdate('Y-m-d H:i:s', time() - 86400 * 30)])->rowCount();
                $b = Db::run('DELETE FROM rate_events WHERE created_at < ?', [gmdate('Y-m-d H:i:s', time() - 86400)])->rowCount();
                $c = Db::run('DELETE FROM audit_log WHERE created_at < ?', [gmdate('Y-m-d H:i:s', time() - 86400 * 365)])->rowCount();
                Audit::log('cleanup', null, "tokens $a, rate $b, audit $c");
                Session::flash('ok', "Removed $a old links, $b rate-limit entries and $c audit entries older than a year.");
                break;
            case 'backup':
                Audit::log('backup_downloaded');
                header('Content-Type: application/sql; charset=utf-8');
                header('Content-Disposition: attachment; filename="bikelog-backup-' . gmdate('Y-m-d-His') . '.sql"');
                Backup::dump(fopen('php://output', 'w'));
                exit;
        }
        redirect('admin_system');
    }
    View::render('admin/system', ['pending' => array_keys(Migrator::pending()), 'applied' => Migrator::applied()], 'System', 'admin');
}

/** Full database dump as SQL (all tables, all users). For the admin's own backups. */
final class Backup
{
    public static function dump($out): void
    {
        $pdo = Db::pdo();
        fwrite($out, "-- Bike Log backup " . gmdate('c') . "\n-- Restore into an EMPTY database (phpMyAdmin → Import).\nSET FOREIGN_KEY_CHECKS=0;\nSET NAMES utf8mb4;\n\n");
        $tables = $pdo->query('SHOW TABLES')->fetchAll(PDO::FETCH_COLUMN);
        foreach ($tables as $t) {
            if (!preg_match('/^[a-z_]+$/', $t)) {
                continue;
            }
            $create = $pdo->query("SHOW CREATE TABLE `$t`")->fetch(PDO::FETCH_NUM)[1];
            fwrite($out, "DROP TABLE IF EXISTS `$t`;\n$create;\n\n");
            $st = $pdo->query("SELECT * FROM `$t`");
            while ($row = $st->fetch(PDO::FETCH_ASSOC)) {
                $vals = array_map(fn($v) => $v === null ? 'NULL' : (is_int($v) || is_float($v) ? (string)$v : $pdo->quote((string)$v)), array_values($row));
                fwrite($out, "INSERT INTO `$t` (`" . implode('`,`', array_keys($row)) . "`) VALUES (" . implode(',', $vals) . ");\n");
            }
            fwrite($out, "\n");
        }
        fwrite($out, "SET FOREIGN_KEY_CHECKS=1;\n");
    }
}
