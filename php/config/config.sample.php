<?php
// Bike Log (PHP) settings. Copy this file to config.php in the same folder and fill it in.
// config.php holds passwords: never commit it, never put it inside the public web folder.
return [
    // MySQL / MariaDB database (your hosting control panel shows these values)
    'db' => [
        'host'    => 'localhost',
        'port'    => 3306,
        'name'    => 'bikelog',
        'user'    => 'bikelog',
        'pass'    => 'change-me',
    ],

    // The address people open in the browser, without a trailing slash. Used in emails (reset links).
    'base_url' => 'https://bikes.example.com',

    // Secret you type once on the install page to create the first admin account.
    // Use 24+ random characters. The install page refuses to run while this is empty.
    'install_key' => '',

    // true: cookies only over HTTPS and http:// requests are redirected. Keep true on a real server.
    'force_https' => true,

    // Only if the site sits behind a reverse proxy/CDN that sets X-Forwarded-For / X-Forwarded-Proto.
    'trust_proxy_headers' => false,

    // How emails are sent:
    //   'smtp' - through your mail provider (recommended; host, port, user, password below)
    //   'mail' - PHP's mail() function (many shared hosts support it; mails may land in spam)
    //   'log'  - write emails to storage/mail.log instead of sending (testing only)
    'mail' => [
        'transport'   => 'smtp',
        'from'        => 'bikelog@example.com',
        'from_name'   => 'Bike Log',
        'smtp_host'   => 'smtp.example.com',
        'smtp_port'   => 587,
        'smtp_secure' => 'tls',   // 'tls' (STARTTLS, port 587) or 'ssl' (port 465)
        'smtp_user'   => 'bikelog@example.com',
        'smtp_pass'   => 'change-me',
    ],

    // Folder for the mail log and the PHP error log. Must be writable and outside the public folder.
    'storage_dir' => __DIR__ . '/../storage',

    // Time zone for new accounts and for "today" when nobody is signed in.
    'default_timezone' => 'Europe/Berlin',
];
