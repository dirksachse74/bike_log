<p class="muted"><?= h(Catalog::typeName($c['component_type'])) ?> <?= h(trim($c['maker'] . ' ' . $c['model'])) ?>
  <?= $c['status'] === 'RETIRED' ? status_badge('RETIRED') . ' since ' . h($c['retired_on']) . ($c['retire_reason'] ? ' (' . h($c['retire_reason']) . ')' : '') : '' ?></p>
<div class="stats">
  <div><span class="big"><?= h(Domain::totalsLabel($totals)) ?></span><span class="muted">lifetime</span></div>
  <div><span class="big"><?= h(number_format($totals['hours'], 1)) ?> h</span><span class="muted">ride time</span></div>
  <div><span class="big"><?= $bike ? h($bike['name']) : '–' ?></span><span class="muted"><?= $bike ? 'on bike now' : ($c['status'] === 'ACTIVE' ? 'spare' : 'retired') ?></span></div>
</div>
<details class="explain"><summary>How the km add up</summary>
  <ul>
    <li>Before tracking: <?= $c['prior_usage'] === 'UNKNOWN' ? 'unknown' : h(km($totals['starting_km'])) . ($c['starting_km_estimate'] ? ' (estimated)' : '') ?></li>
    <li>Rides while installed: <?= h(km($totals['ride_km'])) ?> from <?= (int)$totals['rides'] ?> rides<?= $totals['missing_distance'] ? ' (' . (int)$totals['missing_distance'] . ' without distance)' : '' ?></li>
    <li>Corrections: <?= h(km($totals['adjust_km'])) ?></li>
    <?php if (in_array($c['component_type'], Catalog::INDOOR_EXCLUDED, true)): ?><li>Indoor rides do not count for this part type.</li><?php endif; ?>
  </ul>
</details>
<div class="actions">
  <?php if ($c['status'] === 'ACTIVE'): ?>
  <a class="btn primary" href="<?= h(url('log', ['part' => $c['id']])) ?>">Log maintenance</a>
  <a class="btn" href="<?= h(url('part_install', ['id' => $c['id']])) ?>"><?= $open ? 'Move' : 'Install' ?></a>
  <?php endif; ?>
  <a class="btn" href="<?= h(url('part_edit', ['id' => $c['id']])) ?>">Edit</a>
</div>

<?php if ($reminders): ?>
<section><h2>Reminders</h2><?= View::partial('partials/reminders', ['reminders' => $reminders, 'back' => 'part']) ?></section>
<?php endif; ?>

<?php if ($children): ?>
<section><h2>Mounted on it</h2>
  <table class="list"><?php foreach ($children as $ch): ?>
    <tr><td><span class="muted"><?= h(Catalog::typeName($ch['component_type'])) ?>:</span> <a href="<?= h(url('part', ['id' => $ch['id']])) ?>"><?= h(Domain::componentName($ch)) ?></a></td>
      <td><?= h(Catalog::slotName($ch['slot'])) ?></td><td>since <?= h($ch['installed_on']) ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>

<section><h2>Where it has been</h2>
  <?php if (!$installs): ?><p class="muted">Never installed.</p><?php endif; ?>
  <table class="list">
  <?php foreach ($installs as $i): ?>
    <tr class="<?= $i['voided_at'] ? 'voided' : '' ?>">
      <td><?= $i['bike_id'] ? h($i['bike_name']) : 'on ' . h($i['parent_label']) ?> <span class="muted"><?= h(Catalog::slotName($i['slot'])) ?></span></td>
      <td><?= h($i['installed_on']) ?> → <?= h($i['removed_on'] ?? 'now') ?></td>
      <td class="muted"><?= h($i['removal_reason'] ?? '') ?><?= $i['voided_at'] ? 'Wrong record: ' . h($i['void_reason']) : '' ?></td>
      <td>
        <?php if (!$i['voided_at'] && $i['removed_on'] === null): ?>
          <details class="inline"><summary class="btn small">Remove</summary>
            <form method="post" action="<?= h(url('inst_remove', ['id' => $i['id']])) ?>" class="row"><?= Csrf::field() ?>
              <label>On <input type="date" name="removed_on" value="<?= h(today()) ?>" required></label>
              <label>Why <input type="text" name="reason" placeholder="worn, swapped..."></label>
              <button class="btn small">Remove</button></form>
          </details>
        <?php endif; ?>
        <?php if (!$i['voided_at']): ?>
          <details class="inline"><summary class="btn small">Wrong?</summary>
            <form method="post" action="<?= h(url('inst_void', ['id' => $i['id']])) ?>" class="row"><?= Csrf::field() ?>
              <label>What was wrong <input type="text" name="reason" required></label>
              <button class="btn small danger">Mark as wrong</button>
              <small>For mistakes only. Its rides stop counting for this part. A real change is "Remove".</small></form>
          </details>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </table>
</section>

<section><h2>Maintenance</h2>
  <?php if (!$events): ?><p class="muted">Nothing logged yet.</p><?php endif; ?>
  <table class="list">
  <?php foreach ($events as $e): ?>
    <tr class="<?= $e['voided_at'] ? 'voided' : '' ?>"><td><?= h($e['performed_on']) ?></td><td><?= h(Catalog::actionName($e['action_code'])) ?></td>
      <td><?= h($e['outcome'] ? Catalog::label($e['outcome']) : '') ?><?= $e['measurement_value'] !== null ? ' ' . h((float)$e['measurement_value'] . ' ' . $e['measurement_unit']) : '' ?>
        <?= $e['consumable_name'] ? '<span class="muted">· ' . h($e['consumable_name']) . '</span>' : '' ?> <span class="muted"><?= h($e['notes'] ?? '') ?></span>
        <?= $e['voided_at'] ? '<span class="muted">Wrong entry: ' . h($e['void_reason']) . '</span>' : '' ?></td>
      <td><?php if (!$e['voided_at']): ?><details class="inline"><summary class="btn small">Wrong?</summary>
        <form method="post" action="<?= h(url('event_void', ['id' => $e['id']])) ?>" class="row"><?= Csrf::field() ?>
          <input type="text" name="reason" placeholder="What was wrong" required><button class="btn small danger">Mark as wrong</button></form></details><?php endif; ?></td></tr>
  <?php endforeach; ?>
  </table>
</section>

<details><summary>Service intervals for this part</summary>
  <table class="list">
  <?php foreach ($rules as $r): ?>
    <tr><td><?= h($r['name']) ?><?= $r['component_id'] ? ' <span class="badge b-ok">this part only</span>' : '' ?></td>
      <td><?= h(rule_summary($r)) ?></td>
      <td><?php if ($r['component_id']): ?>
        <a class="btn small" href="<?= h(url('rule_edit', ['id' => $r['id']])) ?>">Change</a>
        <?= post_button('rule_delete', ['id' => $r['id']], 'Use normal interval', 'btn small') ?>
      <?php else: ?>
        <a class="btn small" href="<?= h(url('rule_edit', ['part' => $c['id'], 'code' => $r['rule_code']])) ?>">Change for this part</a>
      <?php endif; ?></td></tr>
  <?php endforeach; ?>
  </table>
  <p><a href="<?= h(url('rules')) ?>">All service intervals</a></p>
</details>

<details><summary>Correct the km</summary>
  <form method="post" action="<?= h(url('adjust', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <?= field('km', 'Km (+ or −)', '', 'text', ['inputmode' => 'decimal', 'required' => true]) ?>
    <?= field('effective_on', 'On', today(), 'date', ['required' => true]) ?>
    <?= field('note', 'Why', '', 'text', ['required' => true]) ?>
    <label class="check"><input type="checkbox" name="is_estimate" value="1"> Estimate</label>
    <button class="btn">Add correction</button>
  </form>
  <table class="list"><?php foreach ($adjustments as $a): ?>
    <tr class="<?= $a['voided_at'] ? 'voided' : '' ?>"><td><?= h($a['effective_on']) ?></td><td class="num"><?= h(km((float)$a['km'], 1)) ?><?= $a['is_estimate'] ? ' (est.)' : '' ?></td><td><?= h($a['note']) ?></td>
      <td><?= $a['voided_at'] ? '' : post_button('adjust', ['id' => $c['id']], 'Void', 'btn small', null, ['do' => 'void', 'adj' => $a['id']]) ?></td></tr>
  <?php endforeach; ?></table>
</details>

<details><summary>Retire</summary>
  <?php if ($c['status'] === 'ACTIVE'): ?>
  <form method="post" action="<?= h(url('part_status', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <input type="hidden" name="do" value="retire">
    <?= field('retired_on', 'On', today(), 'date', ['required' => true]) ?>
    <?= field('reason', 'Why', '', 'text', ['placeholder' => 'worn out, crashed, sold...']) ?>
    <button class="btn">Retire part</button>
  </form>
  <p class="muted">Retiring removes it from the bike on that date. History and km are kept.</p>
  <?php else: ?>
    <?= post_button('part_status', ['id' => $c['id']], 'Make active again', 'btn', null, ['do' => 'restore']) ?>
  <?php endif; ?>
</details>
