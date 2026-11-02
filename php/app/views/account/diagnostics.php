<p class="muted">For finding problems. Share this page with whoever runs the server if something looks wrong.</p>
<section class="card"><h2>Version</h2>
  <p>Bike Log <?= h(BIKELOG_PHP_VERSION) ?> · PHP <?= h($php) ?> · database <?= h($db) ?></p>
  <p class="muted">Database updates applied: <?= h(implode(', ', $applied)) ?></p>
  <?php if ($pending): ?><p><?= status_badge('OVERDUE') ?> Waiting database updates: <?= h(implode(', ', $pending)) ?> (the admin applies them under Admin → System).</p><?php endif; ?>
</section>
<section class="card"><h2>Checks</h2>
  <table class="list"><?php foreach ($checks as $label => $n): ?>
    <tr><td><?= h($label) ?></td><td class="num"><?= $n ? status_badge('ATTENTION') . ' ' . (int)$n : '<span class="muted">none</span>' ?></td></tr>
  <?php endforeach; ?></table>
</section>
<details><summary>Your records per table</summary>
  <table class="list"><?php foreach ($counts as $t => $n): ?><tr><td><code><?= h($t) ?></code></td><td class="num"><?= (int)$n ?></td></tr><?php endforeach; ?></table>
</details>
<p><a class="btn" href="<?= h(url('changes')) ?>">Change log</a> <a class="btn" href="<?= h(url('backups')) ?>">Backups</a></p>
