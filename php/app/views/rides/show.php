<p class="muted"><?= $bike ? '<a href="' . h(url('bike', ['id' => $bike['id']])) . '">' . h($bike['name']) . '</a>' : 'No bike' ?>
  · <?= h(km($ride['distance_km'] === null ? null : (float)$ride['distance_km'], 1)) ?> · <?= h(duration($ride['duration_s'] === null ? null : (int)$ride['duration_s'])) ?>
  <?= $ride['kind'] === 'INDOOR' ? ' · indoor' : '' ?><?= $ride['conditions'] ? ' · ' . h(Catalog::label($ride['conditions'])) : '' ?>
  <?= $ride['removed_at'] ? ' · removed from totals' : '' ?></p>
<?php if ($ride['notes']): ?><p><?= nl2br(h($ride['notes'])) ?></p><?php endif; ?>
<div class="actions"><a class="btn" href="<?= h(url('ride_edit', ['id' => $ride['id']])) ?>">Edit ride</a></div>

<section><h2>Incidents on this ride</h2>
  <?php if (!$incidents): ?><p class="muted">None. A flat, a dropped chain, a broken spoke? Log it below.</p><?php endif; ?>
  <?= View::partial('incidents/cards', ['incidents' => $incidents, 'fixData' => $fixData, 'back' => 'r=ride&id=' . $ride['id']]) ?>
</section>

<section><h2>Log an incident</h2>
  <form method="get" class="row">
    <input type="hidden" name="r" value="ride"><input type="hidden" name="id" value="<?= (int)$ride['id'] ?>">
    <label>What happened<select name="type"><?= options(Incidents::types(), $type, true, 'Choose...') ?></select></label>
    <button class="btn">Next</button>
  </form>
  <?php if ($choices): ?>
  <form method="post" class="card" action="<?= h(url('incident_log', ['ride' => $ride['id']])) ?>"><?= Csrf::field() ?>
    <input type="hidden" name="type" value="<?= h($type) ?>">
    <fieldset><legend>What was affected</legend>
      <?php foreach ($choices as $i => $c): ?>
        <label class="check"><input type="checkbox" name="affected[]" value="<?= h($c['key']) ?>" <?= count($choices) === 1 ? 'checked' : '' ?>> <?= h($c['label']) ?></label>
      <?php endforeach; ?>
    </fieldset>
    <?= field('text', 'What happened (optional)', '', 'text', ['maxlength' => 1000]) ?>
    <label class="check"><input type="checkbox" name="solved" value="1"> Already solved (on the ride day)</label>
    <button class="btn primary">Log incident</button>
  </form>
  <?php endif; ?>
</section>
