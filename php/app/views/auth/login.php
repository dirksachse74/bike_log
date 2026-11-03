<form method="post" class="card narrow" action="<?= h(url('login')) ?>">
  <?= Csrf::field() ?>
  <?= field('email', 'Email', $email, 'email', ['required' => true, 'autocomplete' => 'username', 'autofocus' => true]) ?>
  <?= field('password', 'Password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
  <button class="btn primary wide"><?= h(t('Sign in')) ?></button>
  <p class="links">
    <a href="<?= h(url('forgot')) ?>"><?= h(t('Forgot your password?')) ?></a>
    <?php if (Auth::registrationOpen()): ?> · <a href="<?= h(url('register')) ?>"><?= h(t('Create an account')) ?></a><?php endif; ?>
    · <a href="<?= h(url('resend')) ?>"><?= h(t('Confirmation email missing?')) ?></a>
  </p>
</form>
