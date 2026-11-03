<p class="muted"><?= h(t('Copies of your data stored on the server. A copy is made before every fresh start and every restore, so nothing is lost; the newest {n} are kept. For a copy of your own, use Account → Download all my data.', ['n' => UserBackups::KEEP])) ?></p>
<p><?= post_button('backups', [], t('Store a copy now'), 'btn', null, ['do' => 'save']) ?> <a class="btn" href="<?= h(url('fresh_start')) ?>"><?= h(t('Fresh start…')) ?></a></p>
<?php if (!$rows): ?><p class="muted"><?= h(t('No stored copies yet.')) ?></p><?php endif; ?>
<table class="list">
  <?php foreach ($rows as $r): ?>
  <tr><td class="nowrap"><?= h(local_time($r['created_at'])) ?></td>
    <td><?= h(['BEFORE_RESET' => t('Before a fresh start'), 'BEFORE_RESTORE' => t('Before a restore'), 'MANUAL' => t('Stored by you')][$r['reason']] ?? $r['reason']) ?>
      <span class="muted"><?= h((string)$r['summary']) ?> · <?= h(num($r['size_bytes'] / 1024)) ?> KB</span></td>
    <td><?= post_button('backups', ['id' => $r['id']], t('Download'), 'btn small', null, ['do' => 'download']) ?>
      <details><summary class="btn small"><?= h(t('Restore…')) ?></summary>
        <form method="post" action="<?= h(url('backups', ['id' => $r['id']])) ?>" class="card" data-confirm="<?= h(t('Replace ALL your current data with this copy? (Your current data is stored as a copy first.)')) ?>"><?= Csrf::field() ?>
          <input type="hidden" name="do" value="restore">
          <p><?= h(t('This replaces all your bikes, parts, rides and maintenance with this copy. Your current data is stored as a copy first.')) ?></p>
          <?= field('confirm', t('Type {word}', ['word' => UserBackups::CONFIRM_RESTORE]), '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
          <button class="btn danger"><?= h(t('Restore this copy')) ?></button>
        </form>
      </details></td></tr>
  <?php endforeach; ?>
</table>

<section><h2><?= h(t('Restore from a file')) ?></h2>
  <form method="post" action="<?= h(url('backups')) ?>" enctype="multipart/form-data" class="card" data-confirm="<?= h(t('Replace ALL your current data with the file? (Your current data is stored as a copy first.)')) ?>"><?= Csrf::field() ?>
    <input type="hidden" name="do" value="upload">
    <p class="muted"><?= h(t('A file from Account → Download all my data (this server or another one). Everything in it gets new numbers, so it also moves data between accounts.')) ?></p>
    <label><?= h(t('File')) ?><input type="file" name="file" accept=".json,application/json" required></label>
    <?= field('confirm', t('Type {word}', ['word' => UserBackups::CONFIRM_RESTORE]), '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
    <button class="btn danger"><?= h(t('Restore from file')) ?></button>
  </form>
</section>
