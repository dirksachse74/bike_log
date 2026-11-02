<div class="actions">
  <a class="btn primary" href="<?= h(url('log')) ?>">+ Log maintenance</a>
  <a class="btn" href="<?= h(url('reminders')) ?>">Reminders</a>
  <a class="btn" href="<?= h(url('rules')) ?>">Service intervals</a>
</div>
<?php if (!$events): ?><p class="muted">Nothing logged yet.</p><?php endif; ?>
<table class="list">
  <thead><tr><th>Date</th><th>Work</th><th>Part / bike</th><th>Result</th><th class="num">Cost</th></tr></thead>
  <?php foreach ($events as $e): ?>
  <tr class="<?= $e['voided_at'] ? 'voided' : '' ?>">
    <td><?= h($e['performed_on']) ?></td><td><?= h(Catalog::actionName($e['action_code'])) ?></td>
    <td><?php if ($e['component_id']): ?><a href="<?= h(url('part', ['id' => $e['component_id']])) ?>"><?= h(Domain::componentName($e)) ?></a><?php else: ?>Whole bike<?php endif; ?>
      <span class="muted"><?= h($e['bike_name'] ?? '') ?></span></td>
    <td><?= h($e['outcome'] ? Catalog::label($e['outcome']) : '') ?><?= $e['measurement_value'] !== null ? ' ' . h((float)$e['measurement_value'] . ' ' . $e['measurement_unit']) : '' ?>
      <?= $e['consumable_name'] ? '<span class="muted">' . h($e['consumable_name']) . '</span>' : '' ?></td>
    <td class="num"><?= h(money($e['cost_cents'] === null ? null : (int)$e['cost_cents'])) ?></td>
  </tr>
  <?php endforeach; ?>
</table>
