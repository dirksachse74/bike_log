<form method="post" class="card narrow" action="<?= h(url('login')) ?>">
  <?= Csrf::field() ?>
  <?= field('email', 'Email', $email, 'email', ['required' => true, 'autocomplete' => 'username', 'autofocus' => true]) ?>
  <?= field('password', 'Password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
  <button class="btn primary wide">Sign in</button>
  <p class="links">
    <a href="<?= h(url('forgot')) ?>">Forgot your password?</a>
    <?php if (Auth::registrationOpen()): ?> · <a href="<?= h(url('register')) ?>">Create an account</a><?php endif; ?>
    · <a href="<?= h(url('resend')) ?>">Confirmation email missing?</a>
  </p>
</form>
