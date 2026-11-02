<p class="muted"><?= h(trim($bike['maker'] . ' ' . $bike['model'] . ' ' . $bike['year'])) ?>
  <?= $bike['status'] !== 'ACTIVE' ? status_badge($bike['status']) : '' ?></p>
<div class="stats">
  <div><span class="big"><?= h(km((float)$stats['km'])) ?></span><span class="muted">logged</span></div>
  <div><span class="big"><?= (int)$stats['rides'] ?></span><span class="muted">rides</span></div>
  <div><span class="big"><?= h(duration((int)$stats['s'])) ?></span><span class="muted">ride time</span></div>
</div>
<?php if ($stats['missing']): ?><p class="muted"><?= (int)$stats['missing'] ?> ride(s) have no distance; they are not in the km.</p><?php endif; ?>
<div class="actions">
  <a class="btn primary" href="<?= h(url('ride_edit', ['bike' => $bike['id']])) ?>">+ Ride</a>
  <a class="btn" href="<?= h(url('log', ['bike' => $bike['id']])) ?>">Log maintenance</a>
  <a class="btn" href="<?= h(url('part_edit', ['bike' => $bike['id']])) ?>">Add part to this bike</a>
  <a class="btn" href="<?= h(url('bike_edit', ['id' => $bike['id']])) ?>">Edit</a>
</div>

<?php if ($bike['status'] === 'ACTIVE'): ?>
<section>
  <h2>Needs doing</h2>
  <?= View::partial('partials/reminders', ['reminders' => array_values(array_filter($reminders, fn($r) => $r['status'] !== 'OK')), 'back' => 'bike', 'backId' => $bike['id']]) ?>
</section>
<?php endif; ?>

<section>
  <h2>Installed <?= $date !== today() ? 'on ' . h($date) : 'now' ?></h2>
  <form method="get" class="row inline-form">
    <input type="hidden" name="r" value="bike"><input type="hidden" name="id" value="<?= (int)$bike['id'] ?>">
    <label>What was on it on <input type="date" name="on" value="<?= h($date) ?>"></label><button class="btn small">Show</button>
  </form>
  <?php if (!$parts): ?><p class="muted">No parts recorded<?= $date !== today() ? ' on that date' : '' ?>.</p><?php endif; ?>
  <table class="list">
    <thead><tr><th>Part</th><th>Position</th><th>Since</th><th class="num">Km (lifetime)</th></tr></thead>
    <?php foreach ($parts as $p): ?>
    <tr>
      <td class="depth-<?= (int)$p['depth'] ?>"><span class="muted"><?= h(Catalog::typeName($p['component_type'])) ?>:</span>
        <a href="<?= h(url('part', ['id' => $p['id']])) ?>"><?= h(Domain::componentName($p)) ?></a></td>
      <td><?= h(Catalog::slotName($p['slot'])) ?></td><td><?= h($p['installed_on']) ?></td>
      <td class="num"><?= h(Domain::totalsLabel($p['totals'])) ?></td>
    </tr>
    <?php endforeach; ?>
  </table>
</section>

<section>
  <h2>Recent rides</h2>
  <?php if (!$rides): ?><p class="muted">No rides yet.</p><?php endif; ?>
  <table class="list">
  <?php foreach ($rides as $r): ?>
    <tr><td><?= h($r['ride_date']) ?><?php if (isset($changeDays[$r['ride_date']])): ?> <span class="badge b-soon" title="A part was fitted or removed that day. The ride counts for the part fitted that day.">part change</span><?php endif; ?></td>
      <td><a href="<?= h(url('ride_edit', ['id' => $r['id']])) ?>"><?= h($r['name'] ?: 'Ride') ?></a><?= $r['kind'] === 'INDOOR' ? ' <span class="muted">(indoor)</span>' : '' ?></td>
      <td class="num"><?= h(km($r['distance_km'] === null ? null : (float)$r['distance_km'], 1)) ?></td></tr>
  <?php endforeach; ?>
  </table>
  <p><a href="<?= h(url('rides', ['bike' => $bike['id']])) ?>">All rides of this bike</a></p>
</section>

<details>
  <summary>Maintenance on this bike</summary>
  <table class="list">
  <?php foreach ($events as $e): ?>
    <tr><td><?= h($e['performed_on']) ?></td><td><?= h(Catalog::actionName($e['action_code'])) ?></td>
      <td><?= $e['component_id'] ? '<a href="' . h(url('part', ['id' => $e['component_id']])) . '">' . h($e['label']) . '</a>' : 'Whole bike' ?></td>
      <td><?= h($e['outcome'] ? Catalog::label($e['outcome']) : '') ?></td></tr>
  <?php endforeach; ?>
  </table>
</details>

<details>
  <summary>Part changes (history)</summary>
  <table class="list">
  <?php foreach ($history as $i): ?>
    <tr class="<?= $i['voided_at'] ? 'voided' : '' ?>"><td><a href="<?= h(url('part', ['id' => $i['component_id']])) ?>"><?= h($i['label']) ?></a></td>
      <td><?= h(Catalog::slotName($i['slot'])) ?></td><td><?= h($i['installed_on']) ?> → <?= h($i['removed_on'] ?? 'now') ?></td>
      <td class="muted"><?= h($i['removal_reason'] ?? '') ?><?= $i['voided_at'] ? ' (wrong record: ' . h($i['void_reason']) . ')' : '' ?></td></tr>
  <?php endforeach; ?>
  </table>
</details>

<details>
  <summary>Retire or delete this bike</summary>
  <?php if ($bike['status'] === 'ACTIVE'): ?>
    <?= post_button('bike_status', ['id' => $bike['id']], 'Retire bike', 'btn', 'Retire this bike? Its history stays.', ['do' => 'retire']) ?>
  <?php else: ?>
    <?= post_button('bike_status', ['id' => $bike['id']], 'Make active again', 'btn', null, ['do' => 'restore']) ?>
  <?php endif; ?>
  <?= post_button('bike_status', ['id' => $bike['id']], 'Delete (only without history)', 'btn danger', 'Delete this bike for good?', ['do' => 'delete']) ?>
</details>
