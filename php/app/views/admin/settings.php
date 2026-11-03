<?= View::partial('admin/_nav') ?>
<form method="post" class="card" action="<?= h(url('admin_settings')) ?>"><?= Csrf::field() ?>
  <?= field('site_name', t('Site name'), Settings::get('site_name'), 'text', ['maxlength' => 60]) ?>
  <label><?= h(t('Language for visitors')) ?><select name="default_language"><?= options(I18n::LANGS, Settings::get('default_language'), true, t('From the browser')) ?></select>
    <small><?= h(t('Signed-in users pick their own language (switch at the top, or My settings).')) ?></small></label>
  <label><?= h(t('Who can sign up')) ?><select name="registration"><?= options(['open' => t('Anyone'), 'invite' => t('Only people I invite'), 'closed' => t('Nobody (closed)')], Settings::get('registration')) ?></select></label>
  <?= field('allowed_email_domains', t('Only these email domains (optional)'), Settings::get('allowed_email_domains'), 'text', ['placeholder' => 'example.com, club.de', 'data-help' => t('Comma separated. Empty = any address. Invitations ignore this.')]) ?>
  <label class="check"><input type="checkbox" name="require_verification" value="1" <?= Settings::get('require_verification') === '1' ? 'checked' : '' ?>> <?= h(t('New accounts must confirm their email before signing in (recommended)')) ?></label>
  <label class="check"><input type="checkbox" name="maintenance_mode" value="1" <?= Settings::get('maintenance_mode') === '1' ? 'checked' : '' ?>> <?= h(t('Maintenance mode: only admins can sign in')) ?></label>
  <?= field('notice', t('Notice for everyone (optional)'), Settings::get('notice'), 'text', ['maxlength' => 300, 'data-help' => t('Shown at the top of every page, e.g. "Update on Sunday 20:00".')]) ?>
  <button class="btn primary"><?= h(t('Save')) ?></button>
</form>
<p class="muted"><?= h(t('Mail server, database and install key live in config/config.php on the server, so they never show in the browser.')) ?></p>
