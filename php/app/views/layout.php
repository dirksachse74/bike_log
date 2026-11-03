<?php
$u = Auth::user();
$flash = Session::takeFlash();
unset($_SESSION['old']);
$nav = [['home', 'Overview'], ['bikes', 'Bikes'], ['rides', 'Rides'], ['parts', 'Parts'], ['spares', 'Spares'], ['maintenance', 'Maintenance'], ['supplies', 'Supplies']];
$site = Settings::get('site_name');
?><!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title><?= h(View::$title ? View::$title . ' · ' . $site : $site) ?></title>
<link rel="stylesheet" href="assets/style.css?v=<?= h(BIKELOG_PHP_VERSION) ?>">
<link rel="icon" href="assets/icon.svg" type="image/svg+xml">
<script src="assets/app.js?v=<?= h(BIKELOG_PHP_VERSION) ?>" defer></script>
</head>
<body>
<header class="top">
  <a class="brand" href="<?= h(url('home')) ?>"><img src="assets/icon.svg" alt="" width="26" height="26"> <?= h($site) ?></a>
  <?php if ($u): ?>
  <nav class="main">
    <?php foreach ($nav as [$r, $label]): ?>
      <a href="<?= h(url($r)) ?>" class="<?= View::$active === $r ? 'on' : '' ?>"><?= h($label) ?></a>
    <?php endforeach; ?>
    <?php if ($u['role'] === 'ADMIN'): ?><a href="<?= h(url('admin')) ?>" class="<?= View::$active === 'admin' ? 'on' : '' ?>"><?= h(t('Admin')) ?></a><?php endif; ?>
  </nav>
  <div class="me">
    <a href="<?= h(url('account')) ?>" class="<?= View::$active === 'account' ? 'on' : '' ?>"><?= h($u['display_name']) ?></a>
    <?= post_button('logout', [], 'Sign out', 'btn link') ?>
  </div>
  <?php endif; ?>
</header>
<?php if ($u && Settings::get('notice') !== ''): ?><div class="notice"><?= h(Settings::get('notice')) ?></div><?php endif; ?>
<?php if ($u && $u['role'] === 'ADMIN' && Migrator::pending()): ?>
  <div class="notice warn"><?= h(t('The database needs an update after the last upload.')) ?> <a href="<?= h(url('admin_system')) ?>"><?= h(t('Update now')) ?></a></div>
<?php endif; ?>
<main>
  <?php foreach ($flash as [$type, $msg]): ?>
    <div class="flash <?= h($type) ?>" role="status"><?= h($msg) ?></div>
  <?php endforeach; ?>
  <?php if (View::$title): ?><h1><?= h(View::$title) ?></h1><?php endif; ?>
  <?= $content ?>
</main>
<?php if ($u): ?><datalist id="shops"><?php foreach (PickLists::names((int)$u['id']) as $n): ?><option value="<?= h($n) ?>"><?php endforeach; ?></datalist><?php endif; ?>
<?php if ($u): ?>
<nav class="tabs">
  <a href="<?= h(url('home')) ?>" class="<?= View::$active === 'home' ? 'on' : '' ?>"><?= h(t('Overview')) ?></a>
  <a href="<?= h(url('ride_edit')) ?>" class="plus"><?= h(t('+ Ride')) ?></a>
  <a href="<?= h(url('bikes')) ?>" class="<?= View::$active === 'bikes' ? 'on' : '' ?>"><?= h(t('Bikes')) ?></a>
  <a href="<?= h(url('log')) ?>" class="<?= View::$active === 'maintenance' ? 'on' : '' ?>"><?= h(t('Log work')) ?></a>
</nav>
<?php endif; ?>
<footer><?= h(t('Bike Log')) ?> <?= h(BIKELOG_PHP_VERSION) ?> <?= h(t('· reminders help you plan; they never mean a part is safe.')) ?></footer>
</body>
</html>
