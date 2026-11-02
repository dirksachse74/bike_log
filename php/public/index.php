<?php
declare(strict_types=1);

// Front controller: every page goes through here (index.php?r=<route>).

require __DIR__ . '/../app/bootstrap.php';

// security headers on every response
header("Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'");
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: same-origin');
header('Permissions-Policy: geolocation=(), camera=(), microphone=()');
header('Cache-Control: no-store');

if (Config::get('force_https', true) && !Request::isHttps() && PHP_SAPI !== 'cli-server') {
    header('Location: https://' . ($_SERVER['HTTP_HOST'] ?? '') . ($_SERVER['REQUEST_URI'] ?? '/'), true, 301);
    exit;
}
if (Request::isHttps()) {
    header('Strict-Transport-Security: max-age=31536000');
}

Session::start();

$route = get_param('r', 'home');
$routes = Routes::all();
if (!isset($routes[$route])) {
    $route = 'notfound';
}

try {
    if (Request::isPost()) {
        Csrf::check();
    }
    if (!in_array($route, ['install', 'notfound'], true) && !Installer::isInstalled()) {
        redirect('install');
    }
    ($routes[$route])();
} catch (UserError $e) {
    // a form problem: show it and go back to the form
    Session::flash('error', $e->getMessage());
    $back = $_SERVER['HTTP_REFERER'] ?? '';
    $host = $_SERVER['HTTP_HOST'] ?? '';
    if ($back !== '' && parse_url($back, PHP_URL_HOST) === $host) {
        $_SESSION['old'] = array_diff_key($_POST, ['_csrf' => 1, 'password' => 1, 'password2' => 1, 'current' => 1]);
        header('Location: ' . $back, true, 303);
        exit;
    }
    View::render('message', ['text' => $e->getMessage()], 'Something is not right');
} catch (NotFound $e) {
    if (http_response_code() === 200) {
        http_response_code(404);
    }
    View::render('message', ['text' => $e->getMessage()], 'Not found');
} catch (Throwable $e) {
    error_log('Bike Log error: ' . $e);
    http_response_code(500);
    View::render('message', ['text' => 'Something went wrong on the server. The error was logged; please try again.'], 'Error');
}
