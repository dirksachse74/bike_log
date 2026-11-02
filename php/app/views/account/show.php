<p><a class="btn" href="<?= h(url('my_settings')) ?>">My settings: spares to keep, broken spokes, tire setup</a>
  <a class="btn" href="<?= h(url('lists')) ?>">Shops</a> <a class="btn" href="<?= h(url('changes')) ?>">Change log</a></p>
<section class="card">
  <h2>Profile</h2>
  <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="profile">
    <?= field('display_name', 'Name', $u['display_name'], 'text', ['required' => true, 'maxlength' => 100]) ?>
    <label>Time zone<select name="timezone"><?= options(array_combine(DateTimeZone::listIdentifiers(), DateTimeZone::listIdentifiers()), $u['timezone']) ?></select></label>
    <button class="btn primary">Save</button>
  </form>
</section>
<section class="card">
  <h2>Email</h2>
  <p><?= h($u['email']) ?> <?= $u['email_verified_at'] ? '<span class="badge b-ok">confirmed</span>' : '<span class="badge b-soon">not confirmed</span>' ?></p>
  <details><summary>Change email</summary>
    <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="email">
      <?= field('email', 'New email', '', 'email', ['required' => true]) ?>
      <?= field('current', 'Your password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
      <button class="btn">Send confirmation link</button>
    </form>
  </details>
</section>
<section class="card">
  <h2>Password</h2>
  <form method="post" action="<?= h(url('account')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="password">
    <?= field('current', 'Current password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
    <?= field('password', 'New password', '', 'password', ['required' => true, 'minlength' => Auth::MIN_PASSWORD, 'autocomplete' => 'new-password']) ?>
    <?= field('password2', 'New password again', '', 'password', ['required' => true, 'autocomplete' => 'new-password']) ?>
    <button class="btn">Change password</button>
  </form>
</section>
<section class="card">
  <h2>Devices and data</h2>
  <p><?= post_button('account', [], 'Sign out on all devices', 'btn', null, ['do' => 'logout_all']) ?></p>
  <p><?= post_button('export', [], 'Download all my data (JSON)', 'btn') ?></p>
  <details><summary class="danger-text">Delete my account</summary>
    <form method="post" action="<?= h(url('account')) ?>" data-confirm="Delete your account and ALL your data for good? This cannot be undone."><?= Csrf::field() ?>
      <input type="hidden" name="do" value="delete">
      <p>This deletes your account and all your bikes, parts, rides and maintenance for good. Download your data first if you want to keep it.</p>
      <?= field('current', 'Your password', '', 'password', ['required' => true, 'autocomplete' => 'current-password']) ?>
      <?= field('confirm', 'Type DELETE', '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
      <button class="btn danger">Delete account</button>
    </form>
  </details>
</section>
