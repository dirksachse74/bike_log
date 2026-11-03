<?= View::partial('admin/_nav') ?>
<form method="get" class="row inline-form">
  <input type="hidden" name="r" value="admin_users">
  <input type="search" name="q" value="<?= h($q) ?>" placeholder="<?= h(t('Name or email')) ?>">
  <select name="filter"><?= options(['' => 'All', 'unverified' => 'Email not confirmed', 'blocked' => 'Blocked', 'admins' => 'Admins'], $filter) ?></select>
  <button class="btn small"><?= h(t('Search')) ?></button>
</form>
<table class="list">
  <thead><tr><th><?= h(t('Name')) ?></th><th><?= h(t('Email')) ?></th><th><?= h(t('Role')) ?></th><th><?= h(t('Status')) ?></th><th><?= h(t('Joined')) ?></th><th><?= h(t('Last sign-in')) ?></th><th class="num"><?= h(t('Bikes / rides')) ?></th></tr></thead>
  <?php foreach ($users as $x): ?>
  <tr><td><a href="<?= h(url('admin_user', ['id' => $x['id']])) ?>"><?= h($x['display_name']) ?></a></td><td><?= h($x['email']) ?><?= $x['email_verified_at'] ? '' : ' <span class="badge b-soon">unconfirmed</span>' ?></td>
    <td><?= status_badge($x['role']) ?></td><td><?= status_badge($x['status']) ?></td><td><?= h(substr(local_time($x['created_at']), 0, 10)) ?></td>
    <td><?= h(local_time($x['last_login_at'])) ?: '–' ?></td><td class="num"><?= (int)$x['bikes'] ?> / <?= (int)$x['rides'] ?></td></tr>
  <?php endforeach; ?>
</table>
<section class="card">
  <h2><?= h(t('Invite someone')) ?></h2>
  <form method="post" action="<?= h(url('admin_invite')) ?>" class="row"><?= Csrf::field() ?>
    <?= field('email', 'Email', '', 'email', ['required' => true]) ?><button class="btn primary"><?= h(t('Send invitation')) ?></button>
  </form>
  <p class="muted"><?= h(t('Works in every sign-up mode, also "invite only" and "closed". The link is valid 7 days.')) ?></p>
  <?php if ($invites): ?>
  <table class="list"><?php foreach ($invites as $i): ?>
    <tr><td><?= h($i['email']) ?></td><td class="muted"><?= h(t('by')) ?> <?= h($i['by_name'] ?? '?') ?><?= h(t(', expires')) ?> <?= h(local_time($i['expires_at'])) ?></td>
      <td><?= post_button('admin_invite', [], 'Withdraw', 'btn small', null, ['do' => 'revoke', 'token_id' => $i['id']]) ?></td></tr>
  <?php endforeach; ?></table>
  <?php endif; ?>
</section>
