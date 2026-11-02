<?= View::partial('admin/_nav') ?>
<section class="card">
  <h2>Database updates</h2>
  <?php if ($pending): ?>
    <p>Waiting: <?= h(implode(', ', $pending)) ?>. Download a backup first, then run the update.</p>
    <?= post_button('admin_system', [], 'Update database now', 'btn primary', 'Update the database now? Download a backup first.', ['do' => 'migrate']) ?>
  <?php else: ?>
    <p>Up to date (<?= h(end($applied) ?: 'none') ?>).</p>
  <?php endif; ?>
</section>
<section class="card">
  <h2>Backup</h2>
  <p>Download the whole database (all accounts) as one SQL file. Keep it somewhere safe: it contains everybody's data and password hashes.
    Your hosting's own backups are a good second copy.</p>
  <?= post_button('admin_system', [], 'Download backup (.sql)', 'btn', null, ['do' => 'backup']) ?>
</section>
<section class="card">
  <h2>Email</h2>
  <p>Send a test email to yourself to check the mail settings.</p>
  <?= post_button('admin_system', [], 'Send test email', 'btn', null, ['do' => 'test_mail']) ?>
</section>
<section class="card">
  <h2>Clean up</h2>
  <p>Removes expired links, old rate-limit entries and audit entries older than one year.</p>
  <?= post_button('admin_system', [], 'Clean up now', 'btn', null, ['do' => 'cleanup']) ?>
</section>
