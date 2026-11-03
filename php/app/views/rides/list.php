<div class="actions">
  <a class="btn primary" href="<?= h(url('ride_edit', $bikeId ? ['bike' => $bikeId] : [])) ?>"><?= h(t('+ Add ride')) ?></a>
  <a class="btn" href="<?= h(url('incidents')) ?>"><?= h(t('Incidents')) ?></a>
  <a class="btn" href="<?= h(url('ride_import')) ?>"><?= h(t('Import CSV')) ?></a>
  <form method="get" class="row inline-form">
    <input type="hidden" name="r" value="rides">
    <select name="bike"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?: '', true, 'All bikes') ?></select>
    <select name="show"><?= options(['' => 'Rides', 'removed' => 'Removed rides'], $removed ? 'removed' : '') ?></select>
    <button class="btn small"><?= h(t('Show')) ?></button>
  </form>
</div>
<p class="muted"><?= $count ?> <?= h(t('rides ·')) ?> <?= h(km((float)$sum['km'])) ?> · <?= h(duration((int)$sum['s'])) ?></p>
<form method="post" action="<?= h(url('rides_bulk')) ?>" id="bulk" class="card row"><?= Csrf::field() ?>
  <input type="hidden" name="back_bike" value="<?= $bikeId ?: '' ?>"><input type="hidden" name="back_page" value="<?= $page > 1 ? $page : '' ?>"><input type="hidden" name="back_show" value="<?= $removed ? 'removed' : '' ?>">
  <label><?= h(t('With the ticked rides')) ?><select name="do">
    <?= options($removed ? ['restore' => 'Restore'] : ['bike' => 'Assign the bike below', 'exclude' => 'Leave out of the km (reason below)', 'include' => 'Count again', 'remove' => 'Remove from all totals'], '') ?>
  </select></label>
  <?php if (!$removed): ?>
  <label><?= h(t('Bike')) ?><select name="bike_id"><?= options(array_column(array_filter($bikes, fn($b) => $b['status'] === 'ACTIVE'), 'name', 'id'), '', true, '—') ?></select></label>
  <?= field('reason', 'Reason', '', 'text', ['maxlength' => 255, 'placeholder' => 'rented bike']) ?>
  <?php endif; ?>
  <button class="btn small"><?= h(t('Apply')) ?></button>
</form>
<table class="list">
  <thead><tr><th></th><th><?= h(t('Date')) ?></th><th><?= h(t('Ride')) ?></th><th><?= h(t('Bike')) ?></th><th class="num"><?= h(t('Distance')) ?></th><th class="num"><?= h(t('Time')) ?></th><th></th></tr></thead>
  <?php foreach ($rides as $r): ?>
  <tr class="<?= $r['excluded_reason'] !== null ? 'retired' : '' ?>">
    <td><input type="checkbox" name="ids[]" value="<?= (int)$r['id'] ?>" form="bulk" aria-label="<?= h(t('Select ride')) ?>"></td>
    <td><?= h($r['ride_date']) ?><?php if ($r['bike_id'] && isset($change[$r['bike_id']][$r['ride_date']])): ?> <span class="badge b-soon" title="<?= h(t('A part was fitted or removed on this bike that day. The ride counts for the part fitted that day.')) ?>"><?= h(t('part change')) ?></span><?php endif; ?></td>
    <td><a href="<?= h(url('ride', ['id' => $r['id']])) ?>"><?= h($r['name'] ?: 'Ride') ?></a>
      <?= $r['kind'] === 'INDOOR' ? '<span class="muted">indoor</span>' : '' ?><?= $r['conditions'] === 'WET' ? ' <span class="muted">wet</span>' : '' ?><?= $r['excluded_reason'] !== null ? ' <span class="badge b-unknown" title="' . h($r['excluded_reason']) . '">left out</span>' : '' ?></td>
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
  <?php if ($page > 1): ?><a href="<?= h(url('rides', ['bike' => $bikeId, 'page' => $page - 1, 'show' => $removed ? 'removed' : ''])) ?>"><?= h(t('← Newer')) ?></a><?php endif; ?>
  <?php if ($page * $per < $count): ?><a href="<?= h(url('rides', ['bike' => $bikeId, 'page' => $page + 1, 'show' => $removed ? 'removed' : ''])) ?>"><?= h(t('Older →')) ?></a><?php endif; ?>
</p>
<?php endif; ?>
