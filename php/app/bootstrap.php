<?php
declare(strict_types=1);

error_reporting(E_ALL);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
mb_internal_encoding('UTF-8');

require __DIR__ . '/core.php';
require __DIR__ . '/catalog.php';
require __DIR__ . '/mailer.php';
require __DIR__ . '/auth.php';
require __DIR__ . '/domain.php';
require __DIR__ . '/reminders.php';
require __DIR__ . '/inventory.php';
require __DIR__ . '/groupsets.php';
require __DIR__ . '/incidents.php';
require __DIR__ . '/chains.php';
require __DIR__ . '/money.php';
require __DIR__ . '/records.php';
require __DIR__ . '/products.php';
require __DIR__ . '/backups.php';
require __DIR__ . '/web.php';
require __DIR__ . '/installer.php';
require __DIR__ . '/pages/auth_pages.php';
require __DIR__ . '/pages/bike_pages.php';
require __DIR__ . '/pages/ride_pages.php';
require __DIR__ . '/pages/maintenance_pages.php';
require __DIR__ . '/pages/account_pages.php';
require __DIR__ . '/pages/stock_pages.php';
require __DIR__ . '/pages/incident_pages.php';
require __DIR__ . '/pages/chain_pages.php';
require __DIR__ . '/pages/money_pages.php';
require __DIR__ . '/pages/product_pages.php';
require __DIR__ . '/pages/data_pages.php';
require __DIR__ . '/pages/admin_pages.php';
require __DIR__ . '/routes.php';

$storage = (string)Config::get('storage_dir', __DIR__ . '/../storage');
if (is_dir($storage) && is_writable($storage)) {
    ini_set('error_log', $storage . '/php-error.log');
}
date_default_timezone_set('UTC');
ChangeLog::register();
