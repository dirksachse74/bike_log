<?php $d = $ride['duration_s'] === null ? '' : sprintf('%d:%02d', intdiv((int)$ride['duration_s'], 3600), intdiv((int)$ride['duration_s'] % 3600, 60)); ?>
<form method="post" class="card" action="<?= h(url('ride_edit', ['id' => $ride['id']])) ?>">
  <?= Csrf::field() ?>
  <label><?= h(t('Bike')) ?><select name="bike_id"><?= options(array_column($bikes, 'name', 'id'), old('bike_id', (string)$ride['bike_id']), true, t('No bike (counts for no part)')) ?></select></label>
  <div class="row">
    <?= field('ride_date', t('Date'), old('ride_date', (string)$ride['ride_date']), 'date', ['required' => true]) ?>
    <?= field('distance_km', t('Distance (km)'), old('distance_km', $ride['distance_km'] === null ? '' : rtrim(rtrim((string)$ride['distance_km'], '0'), '.')), 'text', ['inputmode' => 'decimal', 'data-help' => t('Leave empty if unknown: it shows as missing, not 0.')]) ?>
    <?= field('duration', t('Time (h:mm)'), old('duration', $d), 'text', ['placeholder' => '2:15', 'inputmode' => 'numeric']) ?>
  </div>
  <div class="row">
    <label><?= h(t('Where')) ?><select name="kind"><?= options(['OUTDOOR' => t('Outdoor'), 'INDOOR' => t('Indoor, direct-drive trainer (wheels and cassette off)')], old('kind', $ride['kind'])) ?></select></label>
    <label><?= h(t('Conditions')) ?><select name="conditions"><?= options(['DRY' => t('Dry'), 'WET' => t('Wet')], old('conditions', (string)$ride['conditions']), true, t('Not set')) ?></select></label>
  </div>
  <details><summary><?= h(t('More')) ?></summary>
    <?= field('name', t('Name'), old('name', (string)$ride['name']), 'text', ['maxlength' => 200]) ?>
    <div class="row">
      <?= field('start_time', t('Start time'), old('start_time', $ride['start_time'] ? substr((string)$ride['start_time'], 0, 5) : ''), 'time') ?>
      <?= field('elevation_m', t('Climbing (m)'), old('elevation_m', (string)$ride['elevation_m']), 'number', ['min' => 0]) ?>
    </div>
    <?= field('notes', t('Notes'), old('notes', (string)$ride['notes']), 'textarea') ?>
  </details>
  <button class="btn primary"><?= h(t('Save')) ?></button>
  <?php if (!$ride['id']): ?><button class="btn" name="again" value="1"><?= h(t('Save and add another')) ?></button><?php endif; ?>
  <a class="btn" href="<?= h(url('rides')) ?>"><?= h(t('Cancel')) ?></a>
</form>
