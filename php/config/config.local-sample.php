<?php
// Bike Log (PHP) settings for TESTING ON YOUR OWN PC with XAMPP (see LOCAL_TEST_WINDOWS.md).
// Copy this file to config.php in the same folder. Not for a real server: use config.sample.php there.
return [
    // XAMPP's MySQL: user root without a password, only reachable from this PC.
    'db' => [
        'host'    => '127.0.0.1',
        'port'    => 3306,
        'name'    => 'bikelog',
        'user'    => 'root',
        'pass'    => '',
    ],

    // The address start-local.bat opens.
    'base_url' => 'http://127.0.0.1:8080',

    // Typed once on the install page. Any 16+ characters; for a local test this one is fine.
    'install_key' => 'local-test-install-key-2026',

    // No HTTPS on your own PC.
    'force_https' => false,
    'trust_proxy_headers' => false,

    // Emails are not sent: they are written to php\storage\mail.log (open it with Notepad).
    // The password-reset link is in there.
    'mail' => [
        'transport' => 'log',
        'from'      => 'bikelog@localhost',
        'from_name' => 'Bike Log',
    ],

    'storage_dir' => __DIR__ . '/../storage',
    'default_timezone' => 'Europe/Berlin',
];
