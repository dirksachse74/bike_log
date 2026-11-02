<div class="actions">
  <a class="btn primary" href="<?= h(url('ride_edit', $bikeId ? ['bike' => $bikeId] : [])) ?>">+ Add ride</a>
  <form method="get" class="row inline-form">
    <input type="hidden" name="r" value="rides">
    <select name="bike"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?: '', true, 'All bikes') ?></select>
    <select name="show"><?= options(['' => 'Rides', 'removed' => 'Removed rides'], $removed ? 'removed' : '') ?></select>
    <button class="btn small">Show</button>
  </form>
</div>
<p class="muted"><?= $count ?> rides · <?= h(km((float)$sum['km'])) ?> · <?= h(duration((int)$sum['s'])) ?></p>
<table class="list">
  <thead><tr><th>Date</th><th>Ride</th><th>Bike</th><th class="num">Distance</th><th class="num">Time</th><th></th></tr></thead>
  <?php foreach ($rides as $r): ?>
  <tr>
    <td><?= h($r['ride_date']) ?><?php if ($r['bike_id'] && isset($change[$r['bike_id']][$r['ride_date']])): ?> <span class="badge b-soon" title="A part was fitted or removed on this bike that day. The ride counts for the part fitted that day.">part change</span><?php endif; ?></td>
    <td><a href="<?= h(url('ride_edit', ['id' => $r['id']])) ?>"><?= h($r['name'] ?: 'Ride') ?></a>
      <?= $r['kind'] === 'INDOOR' ? '<span class="muted">indoor</span>' : '' ?><?= $r['conditions'] === 'WET' ? ' <span class="muted">wet</span>' : '' ?></td>
    <td><?= h($r['bike_name'] ?? '–') ?></td>
    <td class="num"><?= $r['distance_km'] === null ? '<span class="badge b-unknown">missing</span>' : h(km((float)$r['distance_km'], 1)) ?></td>
    <td class="num"><?= h(duration($r['duration_s'] === null ? null : (int)$r['duration_s'])) ?></td>
    <td><?= $removed ? post_button('ride_status', ['id' => $r['id']], 'Restore', 'btn small', null, ['do' => 'restore'])
        : post_button('ride_status', ['id' => $r['id']], 'Remove', 'btn small', 'Remove this ride from all totals? You can restore it later.', ['do' => 'remove']) ?></td>
  </tr>
  <?php endforeach; ?>
</table>
<?php if ($count > $per): ?>
<p class="pager">
  <?php if ($page > 1): ?><a href="<?= h(url('rides', ['bike' => $bikeId, 'page' => $page - 1, 'show' => $removed ? 'removed' : ''])) ?>">← Newer</a><?php endif; ?>
  <?php if ($page * $per < $count): ?><a href="<?= h(url('rides', ['bike' => $bikeId, 'page' => $page + 1, 'show' => $removed ? 'removed' : ''])) ?>">Older →</a><?php endif; ?>
</p>
<?php endif; ?>
