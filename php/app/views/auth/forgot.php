<form method="post" class="card narrow" action="<?= h(url('forgot')) ?>">
  <?= Csrf::field() ?>
  <p>Enter your email address. If it has an account, we send you a link to choose a new password.</p>
  <?= field('email', 'Email', '', 'email', ['required' => true, 'autocomplete' => 'email', 'autofocus' => true]) ?>
  <button class="btn primary wide">Send link</button>
  <p class="links"><a href="<?= h(url('login')) ?>">Back to sign in</a></p>
</form>
