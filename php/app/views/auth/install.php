<div class="card narrow">
<?php if (!$configOk): ?>
  <p><strong><?= h(t('One step first:')) ?></strong> <?= h(t('open {file} on the server and set {key} to a secret of at least 16 characters. Then reload this page.', ['file' => 'config/config.php', 'key' => 'install_key'])) ?></p>
<?php else: ?>
  <form method="post" action="<?= h(url('install')) ?>">
    <?= Csrf::field() ?>
    <p><?= h(t('This creates the database tables and your admin account. It only works once.')) ?></p>
    <?= field('install_key', t('Install key (from config.php)'), '', 'password', ['required' => true, 'autocomplete' => 'off']) ?>
    <?= field('name', t('Your name'), old('name'), 'text', ['required' => true]) ?>
    <?= field('email', t('Your email'), old('email'), 'email', ['required' => true]) ?>
    <?= field('password', t('Password'), '', 'password', ['required' => true, 'minlength' => Auth::MIN_PASSWORD, 'autocomplete' => 'new-password']) ?>
    <button class="btn primary wide"><?= h(t('Install')) ?></button>
  </form>
<?php endif; ?>
</div>
