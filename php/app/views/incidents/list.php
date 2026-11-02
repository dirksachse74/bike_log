<div class="actions">
  <form method="get" class="row inline-form"><input type="hidden" name="r" value="incidents">
    <select name="show"><?= options(['open' => 'Open', 'all' => 'All', 'removed' => 'Removed'], $show) ?></select><button class="btn small">Show</button></form>
  <a class="btn" href="<?= h(url('punctures')) ?>">Punctures report</a>
</div>
<?php if (!$incidents): ?><p class="muted">Nothing here. Incidents are logged on a ride (open the ride from the ride list).</p><?php endif; ?>
<?= View::partial('incidents/cards', ['incidents' => $incidents, 'fixData' => $fixData, 'back' => 'r=incidents&show=' . $show]) ?>
