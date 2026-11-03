<form method="post" class="card narrow" action="<?= h(url('forgot')) ?>">
  <?= Csrf::field() ?>
  <p><?= h(t('Enter your email address. If it has an account, we send you a link to choose a new password.')) ?></p>
  <?= field('email', t('Email'), '', 'email', ['required' => true, 'autocomplete' => 'email', 'autofocus' => true]) ?>
  <button class="btn primary wide"><?= h(t('Send link')) ?></button>
  <p class="links"><a href="<?= h(url('login')) ?>"><?= h(t('Back to sign in')) ?></a></p>
</form>
