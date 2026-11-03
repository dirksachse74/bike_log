<form method="post" class="card narrow" action="<?= h(url('reset')) ?>">
  <?= Csrf::field() ?>
  <input type="hidden" name="t" value="<?= h($t) ?>">
  <?= field('password', 'New password', '', 'password', ['required' => true, 'minlength' => Auth::MIN_PASSWORD, 'autocomplete' => 'new-password',
      'data-help' => 'At least ' . Auth::MIN_PASSWORD . ' characters.']) ?>
  <?= field('password2', 'New password again', '', 'password', ['required' => true, 'autocomplete' => 'new-password']) ?>
  <button class="btn primary wide"><?= h(t('Save new password')) ?></button>
  <p class="muted"><?= h(t('This signs you out on all other devices.')) ?></p>
</form>
