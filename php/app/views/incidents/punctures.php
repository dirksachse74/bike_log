<p class="muted">Each flat once, and per tire and tube model every physical tire or tube on its own line with its own km. Km are never added up across tires of the same model.</p>
<section><h2>Flats</h2>
  <?php if (!$p['rows']): ?><p class="muted">No flats logged.</p><?php endif; ?>
  <table class="list"><thead><tr><th>Date</th><th>Bike</th><th>Wheel</th><th>Damage</th><th>Tire</th><th>Fixed</th></tr></thead>
  <?php foreach ($p['rows'] as $r): ?>
    <tr><td><?= $r['ride_id'] ? '<a href="' . h(url('ride', ['id' => $r['ride_id']])) . '">' . h($r['on']) . '</a>' : h($r['on']) ?></td><td><?= h($r['bike'] ?? '–') ?></td>
      <td><?= h($r['wheel']) ?></td><td><?= h($r['damage']) ?><?= $r['part'] ? ': ' . h(Domain::componentName($r['part'])) : '' ?></td>
      <td><?= $r['tire'] ? h(Domain::componentName($r['tire'])) : '–' ?></td><td class="muted"><?= h($r['fixed'] ?? 'open') ?><?= $r['conditions'] === 'WET' ? ' · wet' : '' ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php foreach (['TIRE' => 'Tires', 'INNER_TUBE' => 'Inner tubes'] as $type => $title): if (!$p['by_model'][$type]) { continue; } ?>
<section><h2><?= h($title) ?></h2>
  <table class="list"><thead><tr><th>Model</th><th>This one</th><th class="num">Km</th><th class="num">Flats</th><th class="num">Km per flat</th></tr></thead>
  <?php foreach ($p['by_model'][$type] as $model => $items): foreach ($items as $i => $it): ?>
    <tr><td><?= $i === 0 ? h($model) : '' ?></td><td><a href="<?= h(url('part', ['id' => $it['component']['id']])) ?>"><?= h(Domain::componentName($it['component'])) ?></a><?= $it['in_use'] ? ' <span class="muted">in use</span>' : '' ?></td>
      <td class="num"><?= h(km($it['km'])) ?></td><td class="num"><?= (int)$it['punctures'] ?></td><td class="num"><?= $it['km_per_puncture'] !== null ? h(km($it['km_per_puncture'])) : '–' ?></td></tr>
  <?php endforeach; endforeach; ?></table>
</section>
<?php endforeach; ?>
