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
        View::render('message', ['text' => 'Bike Log is installed. Sign in to continue.', 'link' => [url('login'), 'Sign in']], 'Already installed');
        return;
    }
    if (Request::isPost()) {
        $id = Installer::install(post('install_key'), post('email'), post('name'), post('password'));
        $u = Db::one('SELECT * FROM users WHERE id = ?', [$id]);
        Auth::login($u);
        Session::flash('ok', 'Bike Log is installed and you are the admin. Add your first bike.');
        redirect('home');
    }
    View::render('auth/install', ['configOk' => strlen((string)Config::get('install_key', '')) >= 16], 'Install Bike Log');
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
    View::render('auth/login', ['email' => old('email', get_param('email'))], 'Sign in');
}

function page_logout(): void
{
    if (Request::isPost()) {
        if (Auth::id()) {
            Audit::log('logout', Auth::id());
        }
        Auth::logoutLocal();
        Session::flash('ok', 'You are signed out.');
    }
    redirect('login');
}

function page_register(): void
{
    $inviteToken = get_param('invite', post('invite'));
    $invite = $inviteToken !== '' ? Auth::findToken($inviteToken, 'INVITE') : null;
    if ($inviteToken !== '' && !$invite) {
        View::render('message', ['text' => 'This invitation link is invalid, used or expired. Ask the admin for a new one.'], 'Invitation');
        return;
    }
    if (!$invite && !Auth::registrationOpen()) {
        View::render('message', ['text' => Settings::get('registration') === 'invite'
            ? 'Sign-up is by invitation only. Ask the site admin for an invitation.'
            : 'Sign-up is closed at the moment.'], 'Sign up');
        return;
    }
    if (Request::isPost()) {
        if (!RateLimit::allowed('register-ip', Request::ip(), 5, 3600)) {
            throw new UserError('Too many sign-ups from your network. Please try again in an hour.');
        }
        if (post('password') !== post('password2')) {
            throw new UserError('The two passwords are not the same.');
        }
        if (post('website') !== '') {   // honeypot field, invisible to people
            redirect('login');
        }
        RateLimit::hit('register-ip', Request::ip());
        $email = $invite ? (string)$invite['email'] : post('email');
        $id = Db::tx(function () use ($email, $invite) {
            $id = Auth::register($email, post('name'), post('password'), $invite);
            if ($invite && !Auth::consumeToken((int)$invite['id'])) {
                throw new UserError('This invitation was just used.');
            }
            return $id;
        });
        if ($id !== null && $invite) {
            Auth::login(Db::one('SELECT * FROM users WHERE id = ?', [$id]));
            Session::flash('ok', 'Welcome! Your account is ready. Add your first bike.');
            redirect('home');
        }
        if ($id !== null && Settings::get('require_verification') !== '1') {
            Session::flash('ok', 'Your account is ready. Please sign in.');
            redirect('login', ['email' => Auth::normalizeEmail($email)]);
        }
        View::render('message', ['text' => 'Almost done: we sent an email to ' . Auth::normalizeEmail($email)
            . '. Open the link in it to confirm your address, then sign in. (No email after a few minutes? Check the spam folder.)'], 'Check your email');
        return;
    }
    View::render('auth/register', ['invite' => $invite, 'inviteToken' => $inviteToken], 'Create an account');
}

function page_verify(): void
{
    $ok = Auth::verify(get_param('t'));
    View::render('message', [
        'text' => $ok ? 'Thank you, your email address is confirmed. You can sign in now.' : 'This link is invalid, used or expired. Sign in and ask for a new one if needed.',
        'link' => [url('login'), 'Sign in'],
    ], $ok ? 'Email confirmed' : 'Link not valid');
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
        View::render('message', ['text' => 'If that address has an unconfirmed account, a new link is on its way.'], 'Check your email');
        return;
    }
    View::render('auth/resend', [], 'Send the confirmation again');
}

function page_forgot(): void
{
    if (Request::isPost()) {
        Auth::requestReset(post('email'));
        View::render('message', ['text' => 'If an account exists for that address, we sent a link to choose a new password. It works for 1 hour.'], 'Check your email');
        return;
    }
    View::render('auth/forgot', [], 'Forgot your password?');
}

function page_reset(): void
{
    $t = get_param('t', post('t'));
    if (Request::isPost()) {
        if (post('password') !== post('password2')) {
            throw new UserError('The two passwords are not the same.');
        }
        Auth::resetPassword($t, post('password'));
        Auth::logoutLocal();
        Session::flash('ok', 'Your password is changed. Please sign in with the new one.');
        redirect('login');
    }
    if (!Auth::findToken($t, 'RESET')) {
        View::render('message', ['text' => 'This reset link is invalid, used or has expired.', 'link' => [url('forgot'), 'Ask for a new link']], 'Link not valid');
        return;
    }
    View::render('auth/reset', ['t' => $t], 'Choose a new password');
}

function page_confirm_email_change(): void
{
    $row = Auth::findToken(get_param('t'), 'EMAIL_CHANGE');
    if (!$row || !Auth::consumeToken((int)$row['id'])) {
        View::render('message', ['text' => 'This link is invalid, used or expired.'], 'Link not valid');
        return;
    }
    if (Db::one('SELECT id FROM users WHERE email = ?', [$row['email']])) {
        View::render('message', ['text' => 'That address belongs to another account now.'], 'Not changed');
        return;
    }
    $old = Db::one('SELECT email FROM users WHERE id = ?', [$row['user_id']]);
    Db::run('UPDATE users SET email = ?, email_verified_at = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?',
        [$row['email'], now_utc(), now_utc(), $row['user_id']]);
    Audit::log('email_changed', (int)$row['user_id'], $old['email'] . ' -> ' . $row['email'], (int)$row['user_id']);
    Mailer::send($old['email'], 'Your email address was changed', "Hello,\n\nthe email address of your " . Settings::get('site_name')
        . " account was changed to " . $row['email'] . ".\nIf this was not you, contact the site admin right away.\n");
    Auth::logoutLocal();
    View::render('message', ['text' => 'Your new email address is confirmed. Please sign in with it.', 'link' => [url('login'), 'Sign in']], 'Email changed');
}

function page_notfound(): void
{
    http_response_code(404);
    View::render('message', ['text' => 'This page does not exist.'], 'Not found');
}
