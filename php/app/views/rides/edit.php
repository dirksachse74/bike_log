<?php $d = $ride['duration_s'] === null ? '' : sprintf('%d:%02d', intdiv((int)$ride['duration_s'], 3600), intdiv((int)$ride['duration_s'] % 3600, 60)); ?>
<form method="post" class="card" action="<?= h(url('ride_edit', ['id' => $ride['id']])) ?>">
  <?= Csrf::field() ?>
  <label>Bike<select name="bike_id"><?= options(array_column($bikes, 'name', 'id'), old('bike_id', (string)$ride['bike_id']), true, 'No bike (counts for no part)') ?></select></label>
  <div class="row">
    <?= field('ride_date', 'Date', old('ride_date', (string)$ride['ride_date']), 'date', ['required' => true]) ?>
    <?= field('distance_km', 'Distance (km)', old('distance_km', $ride['distance_km'] === null ? '' : rtrim(rtrim((string)$ride['distance_km'], '0'), '.')), 'text', ['inputmode' => 'decimal', 'data-help' => 'Leave empty if unknown: it shows as missing, not 0.']) ?>
    <?= field('duration', 'Time (h:mm)', old('duration', $d), 'text', ['placeholder' => '2:15', 'inputmode' => 'numeric']) ?>
  </div>
  <div class="row">
    <label>Where<select name="kind"><?= options(['OUTDOOR' => 'Outdoor', 'INDOOR' => 'Indoor, direct-drive trainer (wheels and cassette off)'], old('kind', $ride['kind'])) ?></select></label>
    <label>Conditions<select name="conditions"><?= options(['DRY' => 'Dry', 'WET' => 'Wet'], old('conditions', (string)$ride['conditions']), true, 'Not set') ?></select></label>
  </div>
  <details><summary>More</summary>
    <?= field('name', 'Name', old('name', (string)$ride['name']), 'text', ['maxlength' => 200]) ?>
    <div class="row">
      <?= field('start_time', 'Start time', old('start_time', $ride['start_time'] ? substr((string)$ride['start_time'], 0, 5) : ''), 'time') ?>
      <?= field('elevation_m', 'Climbing (m)', old('elevation_m', (string)$ride['elevation_m']), 'number', ['min' => 0]) ?>
    </div>
    <?= field('notes', 'Notes', old('notes', (string)$ride['notes']), 'textarea') ?>
  </details>
  <button class="btn primary">Save</button>
  <?php if (!$ride['id']): ?><button class="btn" name="again" value="1">Save and add another</button><?php endif; ?>
  <a class="btn" href="<?= h(url('rides')) ?>">Cancel</a>
</form>
