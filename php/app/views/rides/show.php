<p class="muted"><?= $bike ? '<a href="' . h(url('bike', ['id' => $bike['id']])) . '">' . h($bike['name']) . '</a>' : 'No bike' ?>
  · <?= h(km($ride['distance_km'] === null ? null : (float)$ride['distance_km'], 1)) ?> · <?= h(duration($ride['duration_s'] === null ? null : (int)$ride['duration_s'])) ?>
  <?= $ride['kind'] === 'INDOOR' ? ' · indoor' : '' ?><?= $ride['conditions'] ? ' · ' . h(Catalog::label($ride['conditions'])) : '' ?>
  <?= $ride['removed_at'] ? ' · removed from totals' : '' ?></p>
<?php if ($ride['notes']): ?><p><?= nl2br(h($ride['notes'])) ?></p><?php endif; ?>
<div class="actions"><a class="btn" href="<?= h(url('ride_edit', ['id' => $ride['id']])) ?>">Edit ride</a></div>
<?php if ($ride['excluded_reason'] !== null): ?>
<div class="card"><p><?= status_badge('UNKNOWN') ?> Left out of the km: <?= h($ride['excluded_reason']) ?>. No part gets km or hours from it.</p>
  <?= post_button('ride_do', ['id' => $ride['id']], 'Count it again', 'btn small', null, ['do' => 'include']) ?></div>
<?php elseif (!$ride['removed_at']): ?>
<details><summary class="btn small link">Leave out of the km…</summary>
  <form method="post" action="<?= h(url('ride_do', ['id' => $ride['id']])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="exclude">
    <?= field('reason', 'Why', '', 'text', ['required' => true, 'maxlength' => 255, 'placeholder' => 'rented bike, logged twice …']) ?><button class="btn small">Leave out</button></form>
</details>
<?php endif; ?>

<?php if ($equipment): ?>
<section><h2>Wheels on this ride</h2>
  <p class="muted">Normally the wheels fitted on the ride day count. Rode other wheels just this once (race wheels)? Pick them here; the km go to them and the parts on them.</p>
  <table class="list"><?php foreach ($equipment as $slot => $e): ?>
    <tr><td><?= h(Catalog::slotName($slot)) ?></td>
      <td><?php if ($e['set']): ?><strong><?= $e['set']['component_id'] ? h(Domain::componentName($e['set'])) : 'none' ?></strong> <span class="muted">(this ride only)</span>
        <?php else: ?><?= $e['fitted'] ? h(Domain::componentName($e['fitted'])) : '<span class="muted">nothing fitted</span>' ?> <span class="muted">(as fitted)</span><?php endif; ?></td>
      <td><form method="post" action="<?= h(url('ride_do', ['id' => $ride['id']])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="equip"><input type="hidden" name="slot" value="<?= h($slot) ?>">
        <select name="part" aria-label="Part for <?= h(Catalog::slotName($slot)) ?>"><option value="">As fitted<?= $e['fitted'] ? ': ' . h(Domain::componentName($e['fitted'])) : '' ?></option><option value="none" <?= $e['set'] && !$e['set']['component_id'] ? 'selected' : '' ?>>None</option>
          <?php foreach ($e['candidates'] as $c): ?><option value="<?= (int)$c['id'] ?>" <?= $e['set'] && (int)$e['set']['component_id'] === (int)$c['id'] ? 'selected' : '' ?>><?= h(Domain::componentName($c)) ?></option><?php endforeach; ?></select>
        <button class="btn small">Set</button></form></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>

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
