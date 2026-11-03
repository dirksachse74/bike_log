<form method="post" class="card narrow" action="<?= h(url('register')) ?>">
  <?= Csrf::field() ?>
  <?php if ($invite): ?>
    <input type="hidden" name="invite" value="<?= h($inviteToken) ?>">
    <p><?= h(t('You were invited as')) ?> <strong><?= h($invite['email']) ?></strong>.</p>
  <?php else: ?>
    <?= field('email', 'Email', old('email'), 'email', ['required' => true, 'autocomplete' => 'email']) ?>
  <?php endif; ?>
  <?= field('name', 'Your name', old('name'), 'text', ['required' => true, 'maxlength' => 100, 'autocomplete' => 'name']) ?>
  <?= field('password', 'Password', '', 'password', ['required' => true, 'minlength' => Auth::MIN_PASSWORD, 'autocomplete' => 'new-password',
      'data-help' => 'At least ' . Auth::MIN_PASSWORD . ' characters. A few random words work well.']) ?>
  <?= field('password2', 'Password again', '', 'password', ['required' => true, 'autocomplete' => 'new-password']) ?>
  <label class="hp" aria-hidden="true"><?= h(t('Leave empty')) ?><input type="text" name="website" tabindex="-1" autocomplete="off"></label>
  <button class="btn primary wide"><?= h(t('Create account')) ?></button>
  <p class="muted"><?= h(t('Your bikes, parts and rides are private to your account. The site admin can see that your account exists, not your data.')) ?></p>
  <p class="links"><a href="<?= h(url('login')) ?>"><?= h(t('I already have an account')) ?></a></p>
</form>
