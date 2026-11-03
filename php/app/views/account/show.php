<p><a class="btn" href="<?= h(url('my_settings')) ?>"><?= h(t('My settings: spares to keep, broken spokes, tire setup')) ?></a>
  <a class="btn" href="<?= h(url('lists')) ?>"><?= h(t('Shops')) ?></a> <a class="btn" href="<?= h(url('changes')) ?>"><?= h(t('Change log')) ?></a>
  <a class="btn" href="<?= h(url('backups')) ?>"><?= h(t('Backups and restore')) ?></a> <a class="btn" href="<?= h(url('diagnostics')) ?>"><?= h(t('Diagnostics')) ?></a></p>
<section class="card">
  <h2><?= h(t('Profile')) ?></h2>
  <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="profile">
    <?= field('display_name', t('Name'), $u['display_name'], 'text', ['required' => true, 'maxlength' => 100]) ?>
    <label><?= h(t('Time zone')) ?><select name="timezone"><?= options(array_combine(DateTimeZone::listIdentifiers(), DateTimeZone::listIdentifiers()), $u['timezone']) ?></select></label>
    <button class="btn primary"><?= h(t('Save')) ?></button>
  </form>
</section>
<section class="card">
  <h2><?= h(t('Email')) ?></h2>
  <p><?= h($u['email']) ?> <?= $u['email_verified_at'] ? '<span class="badge b-ok">' . h(t('confirmed')) . '</span>' : '<span class="badge b-soon">' . h(t('not confirmed')) . '</span>' ?></p>
  <details><summary><?= h(t('Change email')) ?></summary>
    <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="email">
      <?= field('email', t('New email'), '', 'email', ['required' => true]) ?>
      <?= field('current', t('Your password'), '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
      <button class="btn"><?= h(t('Send confirmation link')) ?></button>
    </form>
  </details>
</section>
<section class="card">
  <h2><?= h(t('Password')) ?></h2>
  <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="password">
    <?= field('current', t('Current password'), '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
    <?= field('password', t('New password'), '', 'password', ['required' => true, 'minlength' => Auth::MIN_PASSWORD, 'autocomplete' => 'new-password']) ?>
    <?= field('password2', t('New password again'), '', 'password', ['required' => true, 'autocomplete' => 'new-password']) ?>
    <button class="btn"><?= h(t('Change password')) ?></button>
  </form>
</section>
<section class="card">
  <h2><?= h(t('Devices and data')) ?></h2>
  <p><?= post_button('account', [], t('Sign out on all devices'), 'btn', null, ['do' => 'logout_all']) ?></p>
  <p><?= post_button('export', [], t('Download all my data (JSON)'), 'btn') ?> <a class="btn" href="<?= h(url('backups')) ?>"><?= h(t('Restore…')) ?></a> <a class="btn" href="<?= h(url('fresh_start')) ?>"><?= h(t('Fresh start…')) ?></a></p>
  <details><summary class="danger-text"><?= h(t('Delete my account')) ?></summary>
    <form method="post" action="<?= h(url('account')) ?>" data-confirm="<?= h(t('Delete your account and ALL your data for good? This cannot be undone.')) ?>"><?= Csrf::field() ?>
      <input type="hidden" name="do" value="delete">
      <p><?= h(t('This deletes your account and all your bikes, parts, rides and maintenance for good. Download your data first if you want to keep it.')) ?></p>
      <?= field('current', t('Your password'), '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
      <?= field('confirm', t('Type DELETE'), '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
      <button class="btn danger"><?= h(t('Delete account')) ?></button>
    </form>
  </details>
</section>
