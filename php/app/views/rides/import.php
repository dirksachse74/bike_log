<p class="muted">Add many rides at once from a CSV file: a table you made (columns below) or Strava's own export (strava.com → Settings → My Account → Download your data → <code>activities.csv</code>). A ride that came from the file before is left as it is, so importing the same file again adds nothing new; your edits and removed rides stay.</p>

<?php if ($result): $c = $result['counts']; ?>
<section class="card"><h2><?= $result['dry_run'] ? 'Check' : 'Result' ?>: <?= h($result['file']) ?></h2>
  <p><?= (int)$c['CREATED'] ?> <?= $result['dry_run'] ? 'would be added' : 'added' ?>, <?= (int)$c['EXISTS'] ?> there already, <?= (int)$c['SKIPPED'] ?> skipped (not cycling), <?= (int)$c['ERROR'] ?> with errors.</p>
  <?php if ($result['unknown_bikes']): ?><p><?= status_badge('ATTENTION') ?> Bike names not found (those rides come in without a bike; give them one with the ride list's ticks):
    <?= h(implode(', ', array_map(fn($k, $v) => "$k ($v)", array_keys($result['unknown_bikes']), $result['unknown_bikes']))) ?>. Your bikes: <?= h(implode(', ', $bikes)) ?>.</p><?php endif; ?>
  <?php if ($result['errors']): ?><ul class="errors"><?php foreach ($result['errors'] as $e): ?><li><?= h($e) ?></li><?php endforeach; ?></ul><?php endif; ?>
  <?php if ($result['dry_run'] && $c['CREATED']): ?><p>Looks right? Choose the same file below and press <strong>Import</strong>.</p><?php endif; ?>
</section>
<?php endif; ?>

<form method="post" action="<?= h(url('ride_import')) ?>" enctype="multipart/form-data" class="card"><?= Csrf::field() ?>
  <label>CSV file (up to 20 MB)<input type="file" name="file" accept=".csv,text/csv" required></label>
  <button class="btn" name="do" value="check">Check</button>
  <button class="btn primary" name="do" value="import">Import</button>
</form>

<details><summary class="btn small">Columns of your own CSV</summary>
  <table class="list">
    <tr><td><code>source_id</code></td><td>required: a unique id per ride (e.g. the row number of your sheet); it stops the same ride coming in twice</td></tr>
    <tr><td><code>date</code></td><td>required: <code>2026-05-01</code> or with the start time <code>2026-05-01 07:30</code></td></tr>
    <tr><td><code>distance_km</code> or <code>distance_mi</code></td><td>required column (a cell may be empty = distance unknown)</td></tr>
    <tr><td><code>duration_s</code> or <code>duration_min</code></td><td>optional moving time</td></tr>
    <tr><td><code>name</code>, <code>bike</code></td><td>optional; <code>bike</code> is the bike's name in Bike Log</td></tr>
    <tr><td><code>trainer</code>, <code>wet</code></td><td>optional yes/no: an indoor ride on a direct-drive trainer, a wet ride</td></tr>
    <tr><td><code>sport_type</code>, <code>elevation_m</code></td><td>optional; <code>VirtualRide</code> counts as indoor</td></tr>
  </table>
  <p class="muted">Separator comma or semicolon; with semicolons a decimal comma is read (12,5).</p>
</details>
