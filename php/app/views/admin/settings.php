<?= View::partial('admin/_nav') ?>
<form method="post" class="card" action="<?= h(url('admin_settings')) ?>"><?= Csrf::field() ?>
  <?= field('site_name', 'Site name', Settings::get('site_name'), 'text', ['maxlength' => 60]) ?>
  <label>Who can sign up<select name="registration"><?= options(['open' => 'Anyone', 'invite' => 'Only people I invite', 'closed' => 'Nobody (closed)'], Settings::get('registration')) ?></select></label>
  <?= field('allowed_email_domains', 'Only these email domains (optional)', Settings::get('allowed_email_domains'), 'text', ['placeholder' => 'example.com, club.de', 'data-help' => 'Comma separated. Empty = any address. Invitations ignore this.']) ?>
  <label class="check"><input type="checkbox" name="require_verification" value="1" <?= Settings::get('require_verification') === '1' ? 'checked' : '' ?>> New accounts must confirm their email before signing in (recommended)</label>
  <label class="check"><input type="checkbox" name="maintenance_mode" value="1" <?= Settings::get('maintenance_mode') === '1' ? 'checked' : '' ?>> Maintenance mode: only admins can sign in</label>
  <?= field('notice', 'Notice for everyone (optional)', Settings::get('notice'), 'text', ['maxlength' => 300, 'data-help' => 'Shown at the top of every page, e.g. "Update on Sunday 20:00".']) ?>
  <button class="btn primary">Save</button>
</form>
<p class="muted">Mail server, database and install key live in config/config.php on the server, so they never show in the browser.</p>
