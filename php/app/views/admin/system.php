<?= View::partial('admin/_nav') ?>
<section class="card">
  <h2><?= h(t('Database updates')) ?></h2>
  <?php if ($pending): ?>
    <p><?= h(t('Waiting: {list}. Download a backup first, then run the update.', ['list' => implode(', ', $pending)])) ?></p>
    <?= post_button('admin_system', [], t('Update database now'), 'btn primary', t('Update the database now? Download a backup first.'), ['do' => 'migrate']) ?>
  <?php else: ?>
    <p><?= h(t('Up to date ({last}).', ['last' => end($applied) ?: t('none')])) ?></p>
  <?php endif; ?>
</section>
<section class="card">
  <h2><?= h(t('Backup')) ?></h2>
  <p><?= h(t('Download the whole database (all accounts) as one SQL file. Keep it somewhere safe: it contains everybody\'s data and password hashes. Your hosting\'s own backups are a good second copy.')) ?></p>
  <?= post_button('admin_system', [], t('Download backup (.sql)'), 'btn', null, ['do' => 'backup']) ?>
</section>
<section class="card">
  <h2><?= h(t('Email')) ?></h2>
  <p><?= h(t('Send a test email to yourself to check the mail settings.')) ?></p>
  <?= post_button('admin_system', [], t('Send test email'), 'btn', null, ['do' => 'test_mail']) ?>
</section>
<section class="card">
  <h2><?= h(t('Clean up')) ?></h2>
  <p><?= h(t('Removes expired links, old rate-limit entries and audit entries older than one year.')) ?></p>
  <?= post_button('admin_system', [], t('Clean up now'), 'btn', null, ['do' => 'cleanup']) ?>
</section>
