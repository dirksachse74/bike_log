<p>A fresh start removes all your bikes, parts, rides, maintenance, supplies, products, notes and settings, and starts again with the default service rules. Your account stays.</p>
<p class="muted">Now: <?= h(implode(', ', array_map(fn($k, $v) => "$v $k", array_keys($counts), $counts))) ?>.</p>
<p>Nothing is lost: a copy of everything is stored first and listed under <a href="<?= h(url('backups')) ?>">Backups</a>, where you can restore it.</p>
<form method="post" action="<?= h(url('fresh_start')) ?>" class="card" data-confirm="Remove all your data and start fresh? (A copy is stored first.)"><?= Csrf::field() ?>
  <?= field('current', 'Your password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
  <?= field('confirm', 'Type ' . UserBackups::CONFIRM_RESET, '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
  <button class="btn danger">Start fresh</button>
  <a class="btn" href="<?= h(url('account')) ?>">Cancel</a>
</form>
