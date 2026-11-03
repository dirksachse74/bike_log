<p class="muted"><?= $bike ? '<a href="' . h(url('bike', ['id' => $bike['id']])) . '">' . h($bike['name']) . '</a>' : t('No bike') ?>
  · <?= h(km($ride['distance_km'] === null ? null : (float)$ride['distance_km'], 1)) ?> · <?= h(duration($ride['duration_s'] === null ? null : (int)$ride['duration_s'])) ?>
  <?= $ride['kind'] === 'INDOOR' ? t(' · indoor') : '' ?><?= $ride['conditions'] ? ' · ' . h(Catalog::label($ride['conditions'])) : '' ?>
  <?= $ride['removed_at'] ? t(' · removed from totals') : '' ?></p>
<?php if ($ride['notes']): ?><p><?= nl2br(h($ride['notes'])) ?></p><?php endif; ?>
<div class="actions"><a class="btn" href="<?= h(url('ride_edit', ['id' => $ride['id']])) ?>"><?= h(t('Edit ride')) ?></a></div>
<?php if ($ride['excluded_reason'] !== null): ?>
<div class="card"><p><?= status_badge('UNKNOWN') ?> <?= h(t('Left out of the km: {why}. No part gets km or hours from it.', ['why' => $ride['excluded_reason']])) ?></p>
  <?= post_button('ride_do', ['id' => $ride['id']], t('Count it again'), 'btn small', null, ['do' => 'include']) ?></div>
<?php elseif (!$ride['removed_at']): ?>
<details><summary class="btn small link"><?= h(t('Leave out of the km…')) ?></summary>
  <form method="post" action="<?= h(url('ride_do', ['id' => $ride['id']])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="exclude">
    <?= field('reason', t('Why'), '', 'text', ['required' => true, 'maxlength' => 255, 'placeholder' => t('rented bike, logged twice …')]) ?><button class="btn small"><?= h(t('Leave out')) ?></button></form>
</details>
<?php endif; ?>

<?php if ($equipment): ?>
<section><h2><?= h(t('Wheels on this ride')) ?></h2>
  <p class="muted"><?= h(t('Normally the wheels fitted on the ride day count. Rode other wheels just this once (race wheels)? Pick them here; the km go to them and the parts on them.')) ?></p>
  <table class="list"><?php foreach ($equipment as $slot => $e): ?>
    <tr><td><?= h(Catalog::slotName($slot)) ?></td>
      <td><?php if ($e['set']): ?><strong><?= $e['set']['component_id'] ? h(Domain::componentName($e['set'])) : h(t('none')) ?></strong> <span class="muted"><?= h(t('(this ride only)')) ?></span>
        <?php else: ?><?= $e['fitted'] ? h(Domain::componentName($e['fitted'])) : '<span class="muted">' . h(t('nothing fitted')) . '</span>' ?> <span class="muted"><?= h(t('(as fitted)')) ?></span><?php endif; ?></td>
      <td><form method="post" action="<?= h(url('ride_do', ['id' => $ride['id']])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="equip"><input type="hidden" name="slot" value="<?= h($slot) ?>">
        <select name="part" aria-label="<?= h(t('Part for {slot}', ['slot' => Catalog::slotName($slot)])) ?>"><option value=""><?= h(t('As fitted')) ?><?= $e['fitted'] ? ': ' . h(Domain::componentName($e['fitted'])) : '' ?></option><option value="none" <?= $e['set'] && !$e['set']['component_id'] ? 'selected' : '' ?>><?= h(t('None')) ?></option>
          <?php foreach ($e['candidates'] as $c): ?><option value="<?= (int)$c['id'] ?>" <?= $e['set'] && (int)$e['set']['component_id'] === (int)$c['id'] ? 'selected' : '' ?>><?= h(Domain::componentName($c)) ?></option><?php endforeach; ?></select>
        <button class="btn small"><?= h(t('Set')) ?></button></form></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>

<section><h2><?= h(t('Incidents on this ride')) ?></h2>
  <?php if (!$incidents): ?><p class="muted"><?= h(t('None. A flat, a dropped chain, a broken spoke? Log it below.')) ?></p><?php endif; ?>
  <?= View::partial('incidents/cards', ['incidents' => $incidents, 'fixData' => $fixData, 'back' => 'r=ride&id=' . $ride['id']]) ?>
</section>

<section><h2><?= h(t('Log an incident')) ?></h2>
  <form method="get" class="row">
    <input type="hidden" name="r" value="ride"><input type="hidden" name="id" value="<?= (int)$ride['id'] ?>">
    <label><?= h(t('What happened')) ?><select name="type"><?= options(Incidents::types(), $type, true, t('Choose...')) ?></select></label>
    <button class="btn"><?= h(t('Next')) ?></button>
  </form>
  <?php if ($choices): ?>
  <form method="post" class="card" action="<?= h(url('incident_log', ['ride' => $ride['id']])) ?>"><?= Csrf::field() ?>
    <input type="hidden" name="type" value="<?= h($type) ?>">
    <fieldset><legend><?= h(t('What was affected')) ?></legend>
      <?php foreach ($choices as $i => $c): ?>
        <label class="check"><input type="checkbox" name="affected[]" value="<?= h($c['key']) ?>" <?= count($choices) === 1 ? 'checked' : '' ?>> <?= h($c['label']) ?></label>
      <?php endforeach; ?>
    </fieldset>
    <?= field('text', t('What happened (optional)'), '', 'text', ['maxlength' => 1000]) ?>
    <label class="check"><input type="checkbox" name="solved" value="1"> <?= h(t('Already solved (on the ride day)')) ?></label>
    <button class="btn primary"><?= h(t('Log incident')) ?></button>
  </form>
  <?php endif; ?>
</section>
