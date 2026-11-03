<?php
declare(strict_types=1);

// Sign in, sign up, email confirmation, forgotten password, first-time install.

function old(string $key, string $default = ''): string
{
    $v = $_SESSION['old'][$key] ?? $default;
    return is_string($v) ? $v : $default;
}

function page_install(): void
{
    if (Installer::isInstalled()) {
        View::render('message', ['text' => t('Bike Log is installed. Sign in to continue.'), 'link' => [url('login'), t('Sign in')]], t('Already installed'));
        return;
    }
    if (Request::isPost()) {
        $id = Installer::install(post('install_key'), post('email'), post('name'), post('password'));
        $u = Db::one('SELECT * FROM users WHERE id = ?', [$id]);
        Auth::login($u);
        Session::flash('ok', t('Bike Log is installed and you are the admin. Add your first bike.'));
        redirect('home');
    }
    View::render('auth/install', ['configOk' => strlen((string)Config::get('install_key', '')) >= 16], t('Install Bike Log'));
}

function page_login(): void
{
    if (Auth::user()) {
        redirect('home');
    }
    if (Request::isPost()) {
        Auth::attempt(post('email'), post('password'));
        $after = (string)($_SESSION['after_login'] ?? '');
        unset($_SESSION['after_login']);
        parse_str($after, $q);
        $r = is_string($q['r'] ?? null) ? $q['r'] : 'home';
        if (!isset(Routes::all()[$r]) || in_array($r, ['login', 'logout'], true)) {
            $r = 'home';
        }
        unset($q['r']);
        redirect($r, array_filter($q, 'is_string'));
    }
    View::render('auth/login', ['email' => old('email', get_param('email'))], t('Sign in'));
}

/** The language switch in the header (also on the sign-in pages). Saved on the account and in a cookie. */
function page_set_lang(): void
{
    $lang = post('lang');
    if (Request::isPost() && I18n::valid($lang)) {
        I18n::rememberInCookie($lang);
        if (Auth::id()) {
            try {
                Db::run('UPDATE users SET lang = ? WHERE id = ?', [$lang, Auth::id()]);
            } catch (PDOException) {
                // database update 008 not applied yet: the cookie still works
            }
        }
        I18n::set($lang);
    }
    $back = $_SERVER['HTTP_REFERER'] ?? '';
    $host = (string)preg_replace('/:\d+$/', '', (string)($_SERVER['HTTP_HOST'] ?? ''));
    if ($back !== '' && parse_url($back, PHP_URL_HOST) === $host) {
        $q = (string)parse_url($back, PHP_URL_QUERY);
        parse_str($q, $params);
        $r = is_string($params['r'] ?? null) && isset(Routes::all()[$params['r']]) && $params['r'] !== 'set_lang' ? $params['r'] : 'home';
        unset($params['r']);
        redirect($r, array_filter($params, 'is_string'));
    }
    redirect('home');
}

function page_logout(): void
{
    if (Request::isPost()) {
        if (Auth::id()) {
            Audit::log('logout', Auth::id());
        }
        Auth::logoutLocal();
        Session::flash('ok', t('You are signed out.'));
    }
    redirect('login');
}

function page_register(): void
{
    $inviteToken = get_param('invite', post('invite'));
    $invite = $inviteToken !== '' ? Auth::findToken($inviteToken, 'INVITE') : null;
    if ($inviteToken !== '' && !$invite) {
        View::render('message', ['text' => t('This invitation link is invalid, used or expired. Ask the admin for a new one.')], t('Invitation'));
        return;
    }
    if (!$invite && !Auth::registrationOpen()) {
        View::render('message', ['text' => Settings::get('registration') === 'invite'
            ? t('Sign-up is by invitation only. Ask the site admin for an invitation.')
            : t('Sign-up is closed at the moment.')], t('Sign up'));
        return;
    }
    if (Request::isPost()) {
        if (!RateLimit::allowed('register-ip', Request::ip(), 5, 3600)) {
            throw new UserError(t('Too many sign-ups from your network. Please try again in an hour.'));
        }
        if (post('password') !== post('password2')) {
            throw new UserError(t('The two passwords are not the same.'));
        }
        if (post('website') !== '') {   // honeypot field, invisible to people
            redirect('login');
        }
        RateLimit::hit('register-ip', Request::ip());
        $email = $invite ? (string)$invite['email'] : post('email');
        $id = Db::tx(function () use ($email, $invite) {
            $id = Auth::register($email, post('name'), post('password'), $invite);
            if ($invite && !Auth::consumeToken((int)$invite['id'])) {
                throw new UserError(t('This invitation was just used.'));
            }
            return $id;
        });
        if ($id !== null && $invite) {
            Auth::login(Db::one('SELECT * FROM users WHERE id = ?', [$id]));
            Session::flash('ok', t('Welcome! Your account is ready. Add your first bike.'));
            redirect('home');
        }
        if ($id !== null && Settings::get('require_verification') !== '1') {
            Session::flash('ok', t('Your account is ready. Please sign in.'));
            redirect('login', ['email' => Auth::normalizeEmail($email)]);
        }
        View::render('message', ['text' => t('Almost done: we sent an email to {email}. Open the link in it to confirm your address, then sign in. (No email after a few minutes? Check the spam folder.)',
            ['email' => Auth::normalizeEmail($email)])], t('Check your email'));
        return;
    }
    View::render('auth/register', ['invite' => $invite, 'inviteToken' => $inviteToken], t('Create an account'));
}

function page_verify(): void
{
    $ok = Auth::verify(get_param('t'));
    View::render('message', [
        'text' => $ok ? t('Thank you, your email address is confirmed. You can sign in now.') : t('This link is invalid, used or expired. Sign in and ask for a new one if needed.'),
        'link' => [url('login'), t('Sign in')],
    ], $ok ? t('Email confirmed') : t('Link not valid'));
}

function page_resend(): void
{
    if (Request::isPost()) {
        $email = Auth::normalizeEmail(post('email'));
        if (RateLimit::allowed('resend-ip', Request::ip(), 5, 3600) && RateLimit::allowed('resend-email', $email, 2, 3600)) {
            RateLimit::hit('resend-ip', Request::ip());
            RateLimit::hit('resend-email', $email);
            $u = Db::one('SELECT id, email FROM users WHERE email = ? AND email_verified_at IS NULL AND status = ?', [$email, 'ACTIVE']);
            if ($u) {
                Auth::sendVerification((int)$u['id'], $u['email']);
            }
        }
        View::render('message', ['text' => t('If that address has an unconfirmed account, a new link is on its way.')], t('Check your email'));
        return;
    }
    View::render('auth/resend', [], t('Send the confirmation again'));
}

function page_forgot(): void
{
    if (Request::isPost()) {
        Auth::requestReset(post('email'));
        View::render('message', ['text' => t('If an account exists for that address, we sent a link to choose a new password. It works for 1 hour.')], t('Check your email'));
        return;
    }
    View::render('auth/forgot', [], t('Forgot your password?'));
}

function page_reset(): void
{
    $t = get_param('t', post('t'));
    if (Request::isPost()) {
        if (post('password') !== post('password2')) {
            throw new UserError(t('The two passwords are not the same.'));
        }
        Auth::resetPassword($t, post('password'));
        Auth::logoutLocal();
        Session::flash('ok', t('Your password is changed. Please sign in with the new one.'));
        redirect('login');
    }
    if (!Auth::findToken($t, 'RESET')) {
        View::render('message', ['text' => t('This reset link is invalid, used or has expired.'), 'link' => [url('forgot'), t('Ask for a new link')]], t('Link not valid'));
        return;
    }
    View::render('auth/reset', ['t' => $t], t('Choose a new password'));
}

function page_confirm_email_change(): void
{
    $row = Auth::findToken(get_param('t'), 'EMAIL_CHANGE');
    if (!$row || !Auth::consumeToken((int)$row['id'])) {
        View::render('message', ['text' => t('This link is invalid, used or expired.')], t('Link not valid'));
        return;
    }
    if (Db::one('SELECT id FROM users WHERE email = ?', [$row['email']])) {
        View::render('message', ['text' => t('That address belongs to another account now.')], t('Not changed'));
        return;
    }
    $old = Db::one('SELECT email FROM users WHERE id = ?', [$row['user_id']]);
    Db::run('UPDATE users SET email = ?, email_verified_at = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?',
        [$row['email'], now_utc(), now_utc(), $row['user_id']]);
    Audit::log('email_changed', (int)$row['user_id'], $old['email'] . ' -> ' . $row['email'], (int)$row['user_id']);
    Mailer::send($old['email'], t('Your email address was changed'), t("Hello,\n\nthe email address of your {site} account was changed to {email}.\nIf this was not you, contact the site admin right away.\n",
        ['site' => Settings::get('site_name'), 'email' => $row['email']]));
    Auth::logoutLocal();
    View::render('message', ['text' => t('Your new email address is confirmed. Please sign in with it.'), 'link' => [url('login'), t('Sign in')]], t('Email changed'));
}

function page_notfound(): void
{
    http_response_code(404);
    View::render('message', ['text' => t('This page does not exist.')], t('Not found'));
}
