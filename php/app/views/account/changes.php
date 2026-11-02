<p class="muted">What changed in your data, newest first: new records, edited fields, parts taken off, corrections and undo steps.<?= $bike ? ' Only bike ' . h($bike['name']) . '.' : '' ?><?= $part ? ' Only part ' . h(Domain::componentName($part)) . '.' : '' ?></p>
<form method="get" class="row inline-form">
  <input type="hidden" name="r" value="changes">
  <?php if ($bikeId): ?><input type="hidden" name="bike" value="<?= (int)$bikeId ?>"><?php endif; ?>
  <?php if ($partId): ?><input type="hidden" name="part" value="<?= (int)$partId ?>"><?php endif; ?>
  <select name="entity"><?= options(ChangeLog::ENTITY_LABELS, $entity, true, 'Everything') ?></select>
  <button class="btn small">Filter</button>
  <?php if ($bikeId || $partId): ?><a class="btn small link" href="<?= h(url('changes')) ?>">All bikes and parts</a><?php endif; ?>
</form>
<?php if (!$rows): ?><p class="muted">Nothing recorded yet.</p><?php endif; ?>
<?php include __DIR__ . '/../partials/changes.php'; ?>
<?php if (count($rows) === 200): ?>
<p><a class="btn small" href="<?= h(url('changes', array_filter(['bike' => $bikeId, 'part' => $partId, 'entity' => $entity, 'before' => end($rows)['id']]))) ?>">Older</a></p>
<?php endif; ?>
