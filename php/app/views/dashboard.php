<div class="actions">
  <a class="btn primary" href="<?= h(url('ride_edit')) ?>"><?= h(t('+ Add ride')) ?></a>
  <a class="btn" href="<?= h(url('log')) ?>"><?= h(t('Log maintenance')) ?></a>
  <a class="btn" href="<?= h(url('part_edit')) ?>"><?= h(t('Add part')) ?></a>
</div>
<?php if (!$bikes): ?>
  <div class="card">
    <h2><?= h(t('Welcome!')) ?></h2>
    <p><?= h(t('Start with your bike. Then add the parts you care about (chain, tires, brake pads...) with just a type and a name; details can wait.')) ?></p>
    <a class="btn primary" href="<?= h(url('bike_edit')) ?>"><?= h(t('Add your first bike')) ?></a>
  </div>
<?php endif; ?>
<section>
  <h2><?= h(t('Needs doing')) ?></h2>
  <?= View::partial('partials/reminders', ['reminders' => array_slice($reminders, 0, 12), 'back' => 'home']) ?>
  <?php if (count($reminders) > 12): ?><p><a href="<?= h(url('reminders')) ?>"><?= h(t('All')) ?> <?= count($reminders) ?> <?= h(t('reminders')) ?></a></p><?php endif; ?>
  <?php if ($unknown): ?><p class="muted"><?= $unknown ?> <?= h(t('reminder(s) lack information (for example no service logged yet).')) ?></p><?php endif; ?>
  <p><a href="<?= h(url('reminders')) ?>"><?= h(t('All reminders, including OK and unknown ones')) ?></a></p>
</section>
<section>
  <h2><?= h(t('Bikes')) ?> <small class="muted"><?= h(km($yearKm)) ?> <?= h(t('in')) ?> <?= h($year) ?></small></h2>
  <div class="grid">
  <?php foreach ($bikes as $b): ?>
    <a class="card bike" href="<?= h(url('bike', ['id' => $b['id']])) ?>">
      <strong><?= h($b['name']) ?></strong>
      <span class="muted"><?= h(trim($b['maker'] . ' ' . $b['model'])) ?></span>
      <span class="big"><?= h(km((float)$b['stats']['km'])) ?></span>
      <span class="muted"><?= (int)$b['stats']['rides'] ?> <?= h(t('rides')) ?><?= $b['stats']['missing'] ? ', ' . (int)$b['stats']['missing'] . ' without distance' : '' ?></span>
    </a>
  <?php endforeach; ?>
  </div>
</section>
<?php if ($rides): ?>
<section>
  <h2><?= h(t('Latest rides')) ?></h2>
  <table class="list">
  <?php foreach ($rides as $r): ?>
    <tr><td><?= h($r['ride_date']) ?></td><td><a href="<?= h(url('ride', ['id' => $r['id']])) ?>"><?= h($r['name'] ?: 'Ride') ?></a></td>
      <td><?= h($r['bike_name'] ?? '–') ?></td><td class="num"><?= h(km($r['distance_km'] === null ? null : (float)$r['distance_km'], 1)) ?></td></tr>
  <?php endforeach; ?>
  </table>
</section>
<?php endif; ?>
