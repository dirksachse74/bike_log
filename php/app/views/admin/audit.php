<?= View::partial('admin/_nav') ?>
<form method="get" class="row inline-form">
  <input type="hidden" name="r" value="admin_audit">
  <select name="event"><?= options(array_combine($events, $events), $event, true, 'All events') ?></select>
  <?php if ($userId): ?><input type="hidden" name="user" value="<?= (int)$userId ?>"><?php endif; ?>
  <button class="btn small">Filter</button>
</form>
<table class="list">
  <thead><tr><th>When</th><th>Event</th><th>Account</th><th>By</th><th>Detail</th><th>IP</th></tr></thead>
  <?php foreach ($rows as $a): ?>
  <tr><td><?= h(local_time($a['created_at'])) ?></td><td><?= h($a['event']) ?></td>
    <td><?= $a['subject_user_id'] ? '<a href="' . h(url('admin_user', ['id' => $a['subject_user_id']])) . '">' . h($a['subject_email'] ?? '#' . $a['subject_user_id']) . '</a>' : '' ?></td>
    <td><?= h($a['actor_email'] ?? '') ?></td><td class="muted"><?= h($a['detail'] ?? '') ?></td><td class="muted"><?= h($a['ip']) ?></td></tr>
  <?php endforeach; ?>
</table>
<p class="pager">
  <?php if ($page > 1): ?><a href="<?= h(url('admin_audit', ['event' => $event, 'user' => $userId ?: '', 'page' => $page - 1])) ?>">← Newer</a><?php endif; ?>
  <?php if ($page * $per < $count): ?><a href="<?= h(url('admin_audit', ['event' => $event, 'user' => $userId ?: '', 'page' => $page + 1])) ?>">Older →</a><?php endif; ?>
</p>
