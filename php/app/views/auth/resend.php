<form method="post" class="card narrow" action="<?= h(url('resend')) ?>">
  <?= Csrf::field() ?>
  <p>Enter the email address you signed up with and we send the confirmation link again.</p>
  <?= field('email', 'Email', '', 'email', ['required' => true, 'autocomplete' => 'email']) ?>
  <button class="btn primary wide">Send again</button>
</form>
