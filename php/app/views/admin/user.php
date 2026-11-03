<?= View::partial('admin/_nav') ?>
<p><?= h($u['email']) ?> <?= status_badge($u['role']) ?> <?= status_badge($u['status']) ?>
  <?= $u['email_verified_at'] ? '<span class="badge b-ok">' . h(t('email confirmed')) . '</span>' : '<span class="badge b-soon">' . h(t('email not confirmed')) . '</span>' ?>
  <?= $locked ? '<span class="badge b-overdue">' . h(t('sign-in locked (too many attempts)')) . '</span>' : '' ?></p>
<?php if ($u['blocked_reason']): ?><p class="muted"><?= h(t('Blocked because:')) ?> <?= h($u['blocked_reason']) ?></p><?php endif; ?>
<p class="muted"><?= h(t('Joined {date} · last sign-in {last}', ['date' => local_time($u['created_at']), 'last' => local_time($u['last_login_at']) ?: t('never')])) ?> ·
  <?= h(t('{bikes} bikes, {parts} parts, {rides} rides, {events} maintenance entries. You see counts only, not their data.', ['bikes' => (int)$counts['bikes'], 'parts' => (int)$counts['parts'], 'rides' => (int)$counts['rides'], 'events' => (int)$counts['events']])) ?></p>
<div class="actions">
  <?= post_button('admin_user', ['id' => $u['id']], t('Send password reset link'), 'btn', null, ['do' => 'send_reset']) ?>
  <?php if (!$u['email_verified_at']): ?>
    <?= post_button('admin_user', ['id' => $u['id']], t('Resend confirmation'), 'btn', null, ['do' => 'resend_verify']) ?>
    <?= post_button('admin_user', ['id' => $u['id']], t('Mark email confirmed'), 'btn', t('Only if you are sure the address belongs to this person.'), ['do' => 'verify']) ?>
  <?php endif; ?>
  <?php if ($locked): ?><?= post_button('admin_user', ['id' => $u['id']], t('Clear sign-in lock'), 'btn', null, ['do' => 'unlock']) ?><?php endif; ?>
  <?= post_button('admin_user', ['id' => $u['id']], t('Sign out everywhere'), 'btn', null, ['do' => 'logout_all']) ?>
</div>
<?php if (!$self): ?>
<div class="actions">
  <?php if ($u['status'] === 'ACTIVE'): ?>
    <form method="post" action="<?= h(url('admin_user', ['id' => $u['id']])) ?>" class="row inline-form"><?= Csrf::field() ?>
      <input type="hidden" name="do" value="block"><input type="text" name="reason" placeholder="<?= h(t('Reason (optional)')) ?>"><button class="btn"><?= h(t('Block')) ?></button></form>
  <?php else: ?>
    <?= post_button('admin_user', ['id' => $u['id']], t('Unblock'), 'btn', null, ['do' => 'unblock']) ?>
  <?php endif; ?>
  <?= $u['role'] === 'ADMIN' ? post_button('admin_user', ['id' => $u['id']], t('Remove admin rights'), 'btn', null, ['do' => 'demote'])
      : post_button('admin_user', ['id' => $u['id']], t('Make admin'), 'btn', t('Admins can manage all accounts. Continue?'), ['do' => 'promote']) ?>
</div>
<details><summary class="danger-text"><?= h(t('Delete this account')) ?></summary>
  <form method="post" action="<?= h(url('admin_user', ['id' => $u['id']])) ?>" data-confirm="<?= h(t('Delete this account and all its data for good?')) ?>"><?= Csrf::field() ?>
    <input type="hidden" name="do" value="delete">
    <p><?= h(t('Deletes the account and all its bikes, parts, rides and maintenance for good (for example when the person asks for it). Blocking is the undoable choice.')) ?></p>
    <?= field('confirm_email', t('Type the email address to confirm'), '', 'text', ['required' => true, 'autocomplete' => 'off']) ?>
    <button class="btn danger"><?= h(t('Delete account')) ?></button>
  </form>
</details>
<?php endif; ?>
<section><h2><?= h(t('Account history')) ?></h2>
  <table class="list"><?php foreach ($audit as $a): ?>
    <tr><td><?= h(local_time($a['created_at'])) ?></td><td><?= h($a['event']) ?></td><td class="muted"><?= h($a['detail'] ?? '') ?></td><td class="muted"><?= h($a['ip']) ?></td></tr>
  <?php endforeach; ?></table>
</section>
