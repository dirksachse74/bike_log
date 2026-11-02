<?= View::partial('admin/_nav') ?>
<?php if ($pending): ?><div class="flash error">Database update waiting: <?= h(implode(', ', $pending)) ?>. <a href="<?= h(url('admin_system')) ?>">Run it</a></div><?php endif; ?>
<div class="stats">
  <div><span class="big"><?= (int)$stats['users'] ?></span><span class="muted">accounts</span></div>
  <div><span class="big"><?= (int)$stats['active30'] ?></span><span class="muted">signed in last 30 days</span></div>
  <div><span class="big"><?= (int)$stats['unverified'] ?></span><span class="muted">email not confirmed</span></div>
  <div><span class="big"><?= (int)$stats['blocked'] ?></span><span class="muted">blocked</span></div>
  <div><span class="big"><?= $failed24 ?></span><span class="muted">failed sign-ins (24 h)</span></div>
</div>
<p class="muted">All users together: <?= (int)$data['bikes'] ?> bikes, <?= (int)$data['parts'] ?> parts, <?= (int)$data['rides'] ?> rides, <?= (int)$data['events'] ?> maintenance entries.</p>
<section><h2>Latest events</h2>
  <table class="list"><?php foreach ($recent as $a): ?>
    <tr><td><?= h(local_time($a['created_at'])) ?></td><td><?= h($a['event']) ?></td><td><?= h($a['subject_email'] ?? '') ?></td><td class="muted"><?= h($a['detail'] ?? '') ?></td></tr>
  <?php endforeach; ?></table>
  <p><a href="<?= h(url('admin_audit')) ?>">Full audit log</a></p>
</section>
<section><h2>Server</h2>
  <table class="list">
    <tr><td>Bike Log</td><td><?= h($sys['app']) ?></td></tr>
    <tr><td>PHP</td><td><?= h($sys['php']) ?> <?= $sys['argon'] ? '' : '<span class="muted">(no Argon2id: bcrypt used)</span>' ?></td></tr>
    <tr><td>Database</td><td><?= h($sys['db']) ?></td></tr>
    <tr><td>Email</td><td><?= h($sys['mail']) ?> <?= $sys['mail'] === 'log' ? '<span class="badge b-soon">test mode: emails are not sent</span>' : '' ?></td></tr>
    <tr><td>HTTPS</td><td><?= $sys['https'] ? 'yes' : '<span class="badge b-overdue">no: passwords travel unencrypted</span>' ?></td></tr>
  </table>
</section>
