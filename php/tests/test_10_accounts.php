<?php
declare(strict_types=1);

// Accounts and security, tested through the web pages like a browser would.

$admin = new Browser($base);

// not installed: everything goes to the install page
$admin->get('');
check(str_contains($admin->body, 'Install Bike Log'), 'fresh site shows install page');
check(str_contains($admin->headers['content-security-policy'] ?? '', "default-src 'self'"), 'CSP header set');
check(($admin->headers['x-frame-options'] ?? '') === 'DENY', 'frame protection header');

$admin->post('r=install', ['install_key' => 'wrong-key-wrong-key', 'name' => 'Dirk', 'email' => 'admin@example.test', 'password' => 'correct horse battery']);
check(str_contains($admin->body, 'install key is wrong'), 'wrong install key refused');
$admin->post('r=install', ['install_key' => 'test-install-key-0123456789', 'name' => 'Dirk', 'email' => 'Admin@Example.test', 'password' => 'correct horse battery']);
check(str_contains($admin->body, 'you are the admin'), 'install creates admin and signs in');
Installer::reset();
check(Installer::isInstalled(), 'installed');
$admin->post('r=install', ['install_key' => 'test-install-key-0123456789', 'name' => 'X', 'email' => 'x@example.test', 'password' => 'correct horse battery']);
check(str_contains($admin->body, 'Already installed'), 'install cannot run twice');
check((int)Db::value('SELECT COUNT(*) FROM service_rules WHERE user_id = 1') > 20, 'default service rules copied to admin');

// CSRF: a POST without the token is refused
$admin->post('r=bike_edit', ['name' => 'NoToken'], false);
check(str_contains($admin->body, 'form expired') && !Db::one("SELECT id FROM bikes WHERE name = 'NoToken'"), 'POST without CSRF token refused');
$admin->post('r=bike_edit', ['name' => 'BadToken', '_csrf' => str_repeat('0', 64)]);
check(!Db::one("SELECT id FROM bikes WHERE name = 'BadToken'"), 'POST with wrong CSRF token refused');

// ------------------------------------------------------------------ sign-up with email confirmation
$anna = new Browser($base);
$anna->post('r=register', ['email' => 'anna@example.test', 'name' => 'Anna', 'password' => 'short', 'password2' => 'short']);
check(str_contains($anna->body, 'at least 10'), 'short password refused');
$anna->post('r=register', ['email' => 'anna@example.test', 'name' => 'Anna', 'password' => 'anna-secret-pw', 'password2' => 'anna-secret-pw2']);
check(str_contains($anna->body, 'not the same'), 'password mismatch refused');
$anna->post('r=register', ['email' => 'anna@example.test', 'name' => 'Anna <script>', 'password' => 'anna-secret-pw', 'password2' => 'anna-secret-pw']);
check(str_contains($anna->body, 'Check your email'), 'sign-up asks to check email');
$annaRow = Db::one("SELECT * FROM users WHERE email = 'anna@example.test'");
check($annaRow !== null && $annaRow['email_verified_at'] === null && str_starts_with($annaRow['password_hash'], '$argon2id$'), 'account stored unconfirmed with argon2id hash');
check(!str_contains(json_encode(Db::all('SELECT * FROM user_tokens')), last_link('verify')), 'only token hashes are stored');

$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-secret-pw']);
check(str_contains($anna->body, 'confirm your email'), 'unconfirmed account cannot sign in');
$token = last_link('verify');
check(strlen($token) === 64, 'verification email has a link');
$anna->get('r=verify&t=' . $token);
check(str_contains($anna->body, 'confirmed'), 'verification link works');
$anna->get('r=verify&t=' . $token);
check(str_contains($anna->body, 'not valid'), 'verification link works only once');

// same email again: same answer, owner gets a notice, no second account
$mailsBefore = substr_count(mails(), 'To: anna@example.test');
$x = new Browser($base);
$x->post('r=register', ['email' => 'ANNA@example.test', 'name' => 'Evil', 'password' => 'evil-secret-pw', 'password2' => 'evil-secret-pw']);
check(str_contains($x->body, 'Check your email'), 'existing email: same answer as new');
check((int)Db::value("SELECT COUNT(*) FROM users WHERE email = 'anna@example.test'") === 1, 'no duplicate account');
check(substr_count(mails(), 'To: anna@example.test') === $mailsBefore + 1 && str_contains(mails(), 'Someone tried to sign up'), 'owner is told about the attempt');

// ------------------------------------------------------------------ sign in
$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'wrong-password']);
check(str_contains($anna->body, 'Email or password is wrong'), 'wrong password: generic message');
$y = new Browser($base);
$y->post('r=login', ['email' => 'nobody@example.test', 'password' => 'wrong-password']);
check(str_contains($y->body, 'Email or password is wrong'), 'unknown email: same message');
$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-secret-pw']);
check(str_contains($anna->body, 'Overview') && str_contains($anna->body, 'Anna &lt;script&gt;'), 'sign in works and names are escaped');
check(!str_contains($anna->body, 'Anna <script>'), 'no raw HTML from user input');

// ------------------------------------------------------------------ rate limiting
$z = new Browser($base);
for ($i = 0; $i < 5; $i++) {
    $z->post('r=login', ['email' => 'target@example.test', 'password' => 'guess-' . $i]);
}
$z->post('r=login', ['email' => 'target@example.test', 'password' => 'guess-x']);
check(str_contains($z->body, 'Too many sign-in attempts'), 'login throttled after 5 failures per email');
check((int)Db::value("SELECT COUNT(*) FROM audit_log WHERE event = 'login_throttled'") >= 1, 'throttling is audited');

// ------------------------------------------------------------------ data is private per user
$admin->post('r=bike_edit', ['name' => 'Admin Bike']);
$adminBike = (int)Db::value("SELECT id FROM bikes WHERE name = 'Admin Bike'");
check($adminBike > 0, 'admin adds a bike');
$anna->get('r=bike&id=' . $adminBike);
check($anna->status === 404 && !str_contains($anna->body, 'Admin Bike'), "user cannot open another user's bike");
$anna->post('r=bike_edit&id=' . $adminBike, ['name' => 'Hijacked']);
check(Db::value('SELECT name FROM bikes WHERE id = ?', [$adminBike]) === 'Admin Bike', "user cannot change another user's bike");
$anna->post('r=bike_status&id=' . $adminBike, ['do' => 'delete']);
check((int)Db::value('SELECT COUNT(*) FROM bikes WHERE id = ?', [$adminBike]) === 1, "user cannot delete another user's bike");
$anna->post('r=ride_edit', ['bike_id' => $adminBike, 'ride_date' => '2026-10-01', 'distance_km' => '10']);
check((int)Db::value('SELECT COUNT(*) FROM rides WHERE bike_id = ?', [$adminBike]) === 0, "user cannot add rides to another user's bike");
$anna->get('r=bikes');
check(!str_contains($anna->body, 'Admin Bike'), "another user's bikes are not listed");

// ------------------------------------------------------------------ admin area
$anna->get('r=admin');
check($anna->status === 403, 'normal user gets 403 on admin pages');
$anna->post('r=admin_user&id=1', ['do' => 'demote']);
check(Db::value('SELECT role FROM users WHERE id = 1') === 'ADMIN', 'normal user cannot change roles');
$admin->get('r=admin_users');
check(str_contains($admin->body, 'anna@example.test'), 'admin sees the user list');
$annaId = (int)$annaRow['id'];

// block: Anna's open session ends at once
$admin->post('r=admin_user&id=' . $annaId, ['do' => 'block', 'reason' => 'test']);
$anna->get('r=home');
check(str_contains($anna->body, 'Please sign in'), 'blocked user is signed out at once');
$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-secret-pw']);
check(str_contains($anna->body, 'blocked'), 'blocked user cannot sign in');
$admin->post('r=admin_user&id=' . $annaId, ['do' => 'unblock']);
$admin->post('r=admin_user&id=1', ['do' => 'demote']);
check(Db::value('SELECT role FROM users WHERE id = 1') === 'ADMIN', 'admin cannot demote themselves');

// ------------------------------------------------------------------ password reset
$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-secret-pw']);
$other = new Browser($base);   // a second device of Anna
$other->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-secret-pw']);
$r = new Browser($base);
$r->post('r=forgot', ['email' => 'nobody@example.test']);
$answerUnknown = $r->body;
$r->post('r=forgot', ['email' => 'anna@example.test']);
check(strip_tags($answerUnknown) === strip_tags($r->body), 'reset answer is the same for known and unknown emails');
$t1 = last_link('reset');
$r->post('r=forgot', ['email' => 'anna@example.test']);
$t2 = last_link('reset');
check($t1 !== $t2 && strlen($t2) === 64, 'new reset link sent');
$r->get('r=reset&t=' . $t1);
check(str_contains($r->body, 'not valid'), 'older reset link stops working when a new one is sent');
$r->post('r=reset', ['t' => $t2, 'password' => 'anna-new-password', 'password2' => 'anna-new-password']);
check(str_contains($r->body, 'password is changed'), 'reset sets a new password');
$r->get('r=reset&t=' . $t2);
check(str_contains($r->body, 'not valid'), 'reset link works only once');
$other->get('r=home');
check(str_contains($other->body, 'Please sign in'), 'reset signs out other sessions');
Db::run("UPDATE user_tokens SET expires_at = '2000-01-01 00:00:00' WHERE purpose = 'RESET'");
$r->post('r=forgot', ['email' => 'anna@example.test']);
$t3 = last_link('reset');
Db::run("UPDATE user_tokens SET expires_at = '2000-01-01 00:00:00' WHERE token_hash = ?", [hash('sha256', $t3)]);
$r->get('r=reset&t=' . $t3);
check(str_contains($r->body, 'not valid'), 'expired reset link refused');
$anna->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-new-password']);
check(str_contains($anna->body, 'Overview'), 'sign in with the new password');

// session fixation: the session id changes at sign-in
$f = new Browser($base);
$f->get('r=login');
$jarBefore = (string)file_get_contents((new ReflectionProperty($f, 'jar'))->getValue($f));
$f->post('r=login', ['email' => 'anna@example.test', 'password' => 'anna-new-password']);
$jarAfter = (string)file_get_contents((new ReflectionProperty($f, 'jar'))->getValue($f));
preg_match('/bikelog_sid\s+(\S+)/', $jarBefore, $a1);
preg_match('/bikelog_sid\s+(\S+)/', $jarAfter, $a2);
check(isset($a1[1], $a2[1]) && $a1[1] !== $a2[1], 'session id changes at sign-in');
check(str_contains($jarAfter, '#HttpOnly_'), 'session cookie is HttpOnly');

// ------------------------------------------------------------------ invitations and closed sign-up
$admin->post('r=admin_settings', ['site_name' => 'Bike Log', 'registration' => 'invite', 'require_verification' => '1']);
$g = new Browser($base);
$g->get('r=register');
check(str_contains($g->body, 'invitation only'), 'invite-only mode hides the sign-up form');
$admin->post('r=admin_invite', ['email' => 'ben@example.test']);
$inv = last_link('register');
check(strlen($inv) === 64, 'invitation email sent');
$g->get('r=register&invite=' . $inv);
check(str_contains($g->body, 'ben@example.test'), 'invitation opens the form');
$g->post('r=register', ['invite' => $inv, 'name' => 'Ben', 'password' => 'ben-secret-pw1', 'password2' => 'ben-secret-pw1']);
check(str_contains($g->body, 'Welcome'), 'invited user is signed in directly');
check(Db::value("SELECT email_verified_at FROM users WHERE email = 'ben@example.test'") !== null, 'invited email counts as confirmed');
$h2 = new Browser($base);
$h2->get('r=register&invite=' . $inv);
check(str_contains($h2->body, 'invalid, used or expired'), 'invitation works once');

// ------------------------------------------------------------------ account page
$g->post('r=account', ['do' => 'password', 'current' => 'wrong', 'password' => 'ben-secret-pw2', 'password2' => 'ben-secret-pw2']);
check(str_contains($g->body, 'current password is wrong'), 'password change needs the current password');
$g->post('r=account', ['do' => 'password', 'current' => 'ben-secret-pw1', 'password' => 'ben-secret-pw2', 'password2' => 'ben-secret-pw2']);
check(str_contains($g->body, 'Password changed'), 'password change works and keeps this session');
$g->post('r=account', ['do' => 'email', 'email' => 'ben2@example.test', 'current' => 'ben-secret-pw2']);
$ce = last_link('confirm_email');
$g->get('r=confirm_email&t=' . $ce);
check(Db::value("SELECT email FROM users WHERE email = 'ben2@example.test'") === 'ben2@example.test', 'email change after confirming the new address');
$g->post('r=login', ['email' => 'ben2@example.test', 'password' => 'ben-secret-pw2']);
$g->post('r=export', []);
$export = json_decode($g->body, true);
check(is_array($export) && $export['user']['email'] === 'ben2@example.test' && !isset($export['user']['password_hash']), 'data export works and has no password hash');
$benId = (int)Db::value("SELECT id FROM users WHERE email = 'ben2@example.test'");
$g->post('r=account', ['do' => 'delete', 'current' => 'ben-secret-pw2', 'confirm' => 'DELETE']);
check(Db::value('SELECT COUNT(*) FROM users WHERE id = ?', [$benId]) == 0, 'user can delete their own account');

// admin tools
$admin->get('r=admin_audit');
check(str_contains($admin->body, 'login_failed') && str_contains($admin->body, 'password_reset'), 'audit log lists security events');
$admin->post('r=admin_system', ['do' => 'backup']);
check(str_contains($admin->body, 'CREATE TABLE `users`') && str_contains($admin->body, 'INSERT INTO `users`'), 'admin can download a SQL backup');
$admin->post('r=admin_system', ['do' => 'test_mail']);
check(str_contains($admin->body, 'Test email sent'), 'test email');
$admin->post('r=admin_settings', ['site_name' => 'Bike Log', 'registration' => 'open', 'require_verification' => '1']);
