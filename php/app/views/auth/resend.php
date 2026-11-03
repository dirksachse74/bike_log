<form method="post" class="card narrow" action="<?= h(url('resend')) ?>">
  <?= Csrf::field() ?>
  <p><?= h(t('Enter the email address you signed up with and we send the confirmation link again.')) ?></p>
  <?= field('email', 'Email', '', 'email', ['required' => true, 'autocomplete' => 'email']) ?>
  <button class="btn primary wide"><?= h(t('Send again')) ?></button>
</form>
