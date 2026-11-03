<p class="muted"><?= h(t('What changed in your data, newest first: new records, edited fields, parts taken off, corrections and undo steps.')) ?><?= $bike ? ' ' . h(t('Only bike {name}.', ['name' => $bike['name']])) : '' ?><?= $part ? ' ' . h(t('Only part {name}.', ['name' => Domain::componentName($part)])) : '' ?></p>
<form method="get" class="row inline-form">
  <input type="hidden" name="r" value="changes">
  <?php if ($bikeId): ?><input type="hidden" name="bike" value="<?= (int)$bikeId ?>"><?php endif; ?>
  <?php if ($partId): ?><input type="hidden" name="part" value="<?= (int)$partId ?>"><?php endif; ?>
  <select name="entity"><?= options(t_list(ChangeLog::ENTITY_LABELS), $entity, true, t('Everything')) ?></select>
  <button class="btn small"><?= h(t('Filter')) ?></button>
  <?php if ($bikeId || $partId): ?><a class="btn small link" href="<?= h(url('changes')) ?>"><?= h(t('All bikes and parts')) ?></a><?php endif; ?>
</form>
<?php if (!$rows): ?><p class="muted"><?= h(t('Nothing recorded yet.')) ?></p><?php endif; ?>
<?php include __DIR__ . '/../partials/changes.php'; ?>
<?php if (count($rows) === 200): ?>
<p><a class="btn small" href="<?= h(url('changes', array_filter(['bike' => $bikeId, 'part' => $partId, 'entity' => $entity, 'before' => end($rows)['id']]))) ?>"><?= h(t('Older')) ?></a></p>
<?php endif; ?>
