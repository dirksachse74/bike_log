<p class="muted"><?= h(t('Each flat once, and per tire and tube model every physical tire or tube on its own line with its own km. Km are never added up across tires of the same model.')) ?></p>
<section><h2><?= h(t('Flats')) ?></h2>
  <?php if (!$p['rows']): ?><p class="muted"><?= h(t('No flats logged.')) ?></p><?php endif; ?>
  <table class="list"><thead><tr><th><?= h(t('Date')) ?></th><th><?= h(t('Bike')) ?></th><th><?= h(t('Wheel')) ?></th><th><?= h(t('Damage')) ?></th><th><?= h(t('Tire')) ?></th><th><?= h(t('Fixed')) ?></th></tr></thead>
  <?php foreach ($p['rows'] as $r): ?>
    <tr><td><?= $r['ride_id'] ? '<a href="' . h(url('ride', ['id' => $r['ride_id']])) . '">' . h($r['on']) . '</a>' : h($r['on']) ?></td><td><?= h($r['bike'] ?? '–') ?></td>
      <td><?= h($r['wheel']) ?></td><td><?= h($r['damage']) ?><?= $r['part'] ? ': ' . h(Domain::componentName($r['part'])) : '' ?></td>
      <td><?= $r['tire'] ? h(Domain::componentName($r['tire'])) : '–' ?></td><td class="muted"><?= h($r['fixed'] ?? t('open')) ?><?= $r['conditions'] === 'WET' ? t(' · wet') : '' ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php foreach (['TIRE' => t('Tires'), 'INNER_TUBE' => t('Inner tubes')] as $type => $title): if (!$p['by_model'][$type]) { continue; } ?>
<section><h2><?= h($title) ?></h2>
  <table class="list"><thead><tr><th><?= h(t('Model')) ?></th><th><?= h(t('This one')) ?></th><th class="num"><?= h(t('Km')) ?></th><th class="num"><?= h(t('Flats')) ?></th><th class="num"><?= h(t('Km per flat')) ?></th></tr></thead>
  <?php foreach ($p['by_model'][$type] as $model => $items): foreach ($items as $i => $it): ?>
    <tr><td><?= $i === 0 ? h($model) : '' ?></td><td><a href="<?= h(url('part', ['id' => $it['component']['id']])) ?>"><?= h(Domain::componentName($it['component'])) ?></a><?= $it['in_use'] ? ' <span class="muted">' . h(t('in use')) . '</span>' : '' ?></td>
      <td class="num"><?= h(km($it['km'])) ?></td><td class="num"><?= (int)$it['punctures'] ?></td><td class="num"><?= $it['km_per_puncture'] !== null ? h(km($it['km_per_puncture'])) : '–' ?></td></tr>
  <?php endforeach; endforeach; ?></table>
</section>
<?php endforeach; ?>
