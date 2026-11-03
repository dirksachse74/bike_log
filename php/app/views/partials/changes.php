<table class="list changes">
  <?php foreach ($rows as $r): ?>
  <tr><td class="muted nowrap"><?= h(local_time($r['changed_at'])) ?></td>
    <td><?= h(t(ChangeLog::ENTITY_LABELS[$r['entity']] ?? $r['entity'])) ?></td>
    <td><?php if ($r['action'] === 'CHANGED'): ?><?= h(ChangeLog::fieldLabel($r['field'])) ?>: <span class="muted"><?= h($r['old_value'] ?? '–') ?></span> → <?= h($r['new_value'] ?? '–') ?>
      <?php elseif ($r['action'] === 'CREATED'): ?><?= h(t('New:')) ?> <?= h($r['new_value'] ?? '') ?>
      <?php else: ?><?= h($r['new_value'] ?? '') ?><?php endif; ?>
      <?= $r['source'] && $r['source'] !== 'FORM' ? ' <span class="muted">(' . h(t(strtolower(str_replace('_', ' ', $r['source'])))) . ')</span>' : '' ?></td></tr>
  <?php endforeach; ?>
</table>
