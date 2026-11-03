<p class="muted"><?= h(t('For finding problems. Share this page with whoever runs the server if something looks wrong.')) ?></p>
<section class="card"><h2><?= h(t('Version')) ?></h2>
  <p>Bike Log <?= h(BIKELOG_PHP_VERSION) ?> · PHP <?= h($php) ?> · <?= h(t('database')) ?> <?= h($db) ?></p>
  <p class="muted"><?= h(t('Database updates applied:')) ?> <?= h(implode(', ', $applied)) ?></p>
  <?php if ($pending): ?><p><?= status_badge('OVERDUE') ?> <?= h(t('Waiting database updates: {list} (the admin applies them under Admin → System).', ['list' => implode(', ', $pending)])) ?></p><?php endif; ?>
</section>
<section class="card"><h2><?= h(t('Checks')) ?></h2>
  <table class="list"><?php foreach ($checks as $label => $n): ?>
    <tr><td><?= h(t($label)) ?></td><td class="num"><?= $n ? status_badge('ATTENTION') . ' ' . (int)$n : '<span class="muted">' . h(t('none')) . '</span>' ?></td></tr>
  <?php endforeach; ?></table>
</section>
<details><summary><?= h(t('Your records per table')) ?></summary>
  <table class="list"><?php foreach ($counts as $t => $n): ?><tr><td><code><?= h($t) ?></code></td><td class="num"><?= (int)$n ?></td></tr><?php endforeach; ?></table>
</details>
<p><a class="btn" href="<?= h(url('changes')) ?>"><?= h(t('Change log')) ?></a> <a class="btn" href="<?= h(url('backups')) ?>"><?= h(t('Backups')) ?></a></p>
