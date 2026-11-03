<div class="actions">
  <form method="get" class="row inline-form"><input type="hidden" name="r" value="incidents">
    <select name="show"><?= options(['open' => t('Open'), 'all' => t('All'), 'removed' => t('Removed')], $show) ?></select><button class="btn small"><?= h(t('Show')) ?></button></form>
  <a class="btn" href="<?= h(url('punctures')) ?>"><?= h(t('Punctures report')) ?></a>
</div>
<?php if (!$incidents): ?><p class="muted"><?= h(t('Nothing here. Incidents are logged on a ride (open the ride from the ride list).')) ?></p><?php endif; ?>
<?= View::partial('incidents/cards', ['incidents' => $incidents, 'fixData' => $fixData, 'back' => 'r=incidents&show=' . $show]) ?>
