<p class="muted"><?= h(Catalog::typeName($c['component_type'])) ?> <?= h(trim($c['maker'] . ' ' . $c['model'])) ?>
  <?= $c['status'] === 'RETIRED' ? status_badge('RETIRED') . ' ' . h(t('since {date}', ['date' => $c['retired_on']])) . ($c['retire_reason'] ? ' (' . h($c['retire_reason']) . ')' : '') : '' ?></p>
<div class="stats">
  <div><span class="big"><?= h(Domain::totalsLabel($totals)) ?></span><span class="muted"><?= h(t('lifetime')) ?></span></div>
  <div><span class="big"><?= h(num($totals['hours'], 1)) ?> <?= h(t('h')) ?></span><span class="muted"><?= h(t('ride time')) ?></span></div>
  <div><span class="big"><?= $bike ? h($bike['name']) : '–' ?></span><span class="muted"><?= h($bike ? t('on bike now') : ($c['status'] === 'ACTIVE' ? t('spare') : t('retired'))) ?></span></div>
</div>
<details class="explain"><summary><?= h(t('How the km add up')) ?></summary>
  <ul>
    <li><?= h(t('Before tracking:')) ?> <?= $c['prior_usage'] === 'UNKNOWN' ? h(t('unknown')) : h(km($totals['starting_km'])) . ($c['starting_km_estimate'] ? t(' (estimated)') : '') ?></li>
    <li><?= h(t('Rides while installed:')) ?> <?= h(t('{km} from {n} rides', ['km' => km($totals['ride_km']), 'n' => (int)$totals['rides']])) ?><?= $totals['missing_distance'] ? ' ' . h(t('({n} without distance)', ['n' => (int)$totals['missing_distance']])) : '' ?></li>
    <li><?= h(t('Corrections:')) ?> <?= h(km($totals['adjust_km'])) ?></li>
    <?php if (in_array($c['component_type'], Catalog::INDOOR_EXCLUDED, true)): ?><li><?= h(t('Indoor rides do not count for this part type.')) ?></li><?php endif; ?>
  </ul>
</details>
<div class="actions">
  <?php if ($c['status'] === 'ACTIVE'): ?>
  <a class="btn primary" href="<?= h(url('log', ['part' => $c['id']])) ?>"><?= h(t('Log maintenance')) ?></a>
  <?php if ($open): ?><a class="btn" href="<?= h(url('part_replace', ['id' => $c['id']])) ?>"><?= h(t('Replace')) ?></a><?php endif; ?>
  <a class="btn" href="<?= h(url('part_install', ['id' => $c['id']])) ?>"><?= $open ? t('Move') : t('Install') ?></a>
  <?php endif; ?>
  <a class="btn" href="<?= h(url('part_edit', ['id' => $c['id']])) ?>"><?= h(t('Edit')) ?></a>
  <a class="btn link" href="<?= h(url('changes', ['part' => $c['id']])) ?>"><?= h(t('Change log')) ?></a>
</div>

<?php if (Domain::isRiderGear($c['component_type']) && $c['status'] === 'ACTIVE'): $inUse = $c['disposition'] === 'IN_USE'; ?>
<div class="card">
  <p><?= $inUse ? status_badge('ACTIVE') . ' ' . h(t('In use since {date}: every ride counts, on any bike (and for the cleats on these shoes).', ['date' => (string)$c['disposition_on']]))
      : t('Not in use. While shoes are in use, every ride counts for them and for their cleats.') ?></p>
  <form method="post" action="<?= h(url('part_in_use', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <input type="hidden" name="in_use" value="<?= $inUse ? '0' : '1' ?>">
    <?= field('on', $inUse ? t('Put away on') : t('In use from'), today(), 'date', ['required' => true]) ?>
    <button class="btn <?= $inUse ? '' : 'primary' ?>"><?= $inUse ? t('Put away') : t('Start using') ?></button>
  </form>
</div>
<?php endif; ?>

<?php if ($c['disposition'] !== 'STORED' || $c['storage_location'] || $c['tire_setup'] || $c['pressure_note'] || $c['warranty_until'] || $product): ?>
<p class="muted">
  <?= !$open && $c['status'] === 'ACTIVE' ? h(Catalog::raw('dispositions')[$c['disposition']] ?? $c['disposition']) . ($c['storage_location'] ? ' · ' . h($c['storage_location']) : '') . ' · ' : '' ?>
  <?= $c['tire_setup'] ? h(Catalog::raw('tire_setups')[$c['tire_setup']] ?? $c['tire_setup']) . ' · ' : '' ?>
  <?= $c['pressure_note'] ? h(t('Pressure {p}', ['p' => $c['pressure_note']])) . ' · ' : '' ?>
  <?= $c['warranty_until'] ? h(t('Warranty until {date}', ['date' => $c['warranty_until']])) . ' · ' : '' ?>
  <?= $product ? h(t('Product:')) . ' <a href="' . h(url('product', ['id' => $product['id']])) . '">' . h(trim($product['maker'] . ' ' . $product['model'])) . '</a>' : '' ?>
</p>
<?php endif; ?>

<?php if ($bundle): ?><p class="muted"><?= h(t('Bought together:')) ?> <a href="<?= h(url('bundles')) ?>"><?= h($bundle['name']) ?></a><?= $bundle['price_cents'] !== null ? ' ' . h(t('({price} for all)', ['price' => money((int)$bundle['price_cents'])])) : '' ?></p><?php endif; ?>
<?php if ($order): ?>
<div class="card"><p><?= status_badge('SOON') ?> <?= h(t('Away for repair since {date}', ['date' => $order['sent_on']])) ?><?= $order['shop'] ? ' ' . h(t('at {shop}', ['shop' => $order['shop']])) : '' ?><?= $order['reason'] ? ': ' . h($order['reason']) : '' ?></p>
  <details><summary class="btn small primary"><?= h(t('It is back')) ?></summary>
    <form method="post" action="<?= h(url('repair_back', ['id' => $order['id']])) ?>" class="card"><?= Csrf::field() ?>
      <div class="row">
        <?= field('on', t('Back on'), today(), 'date', ['required' => true]) ?>
        <label><?= h(t('What came back')) ?><select name="outcome"><?= options(t_list(ServiceOrders::OUTCOMES), 'REPAIRED_PAID') ?></select></label>
        <?= field('cost', t('Cost'), '', 'text', ['inputmode' => 'decimal']) ?>
        <?= field('receipt', t('Receipt / RMA no.'), '') ?>
      </div>
      <?php if ($order['from_slot']): ?><label class="check"><input type="checkbox" name="put_back" value="1" checked> <?= h(t('Put it back where it was (a part fitted meanwhile is stored)')) ?></label><?php endif; ?>
      <label><?= h(t('If not repaired')) ?><select name="keep_as"><?= options(['STORED' => t('Keep it (stored)'), 'DISCARDED' => t('Discard it')], 'STORED') ?></select></label>
      <details><summary><?= h(t('Replaced under warranty: the new part')) ?></summary><div class="row">
        <?= field('new_label', t('Name'), '') ?><?= field('new_serial', t('Serial number'), '') ?><?= field('new_warranty', t('Warranty until'), '', 'date') ?></div></details>
      <?= field('notes', t('Notes'), '') ?>
      <button class="btn primary"><?= h(t('Save')) ?></button>
    </form>
  </details>
</div>
<?php endif; ?>

<?php if ($reminders): ?>
<section><h2><?= h(t('Reminders')) ?></h2><?= View::partial('partials/reminders', ['reminders' => $reminders, 'back' => 'part']) ?></section>
<?php endif; ?>

<?php if ($children): ?>
<section><h2><?= h(t('Mounted on it')) ?></h2>
  <table class="list"><?php foreach ($children as $ch): ?>
    <tr><td><span class="muted"><?= h(Catalog::typeName($ch['component_type'])) ?>:</span> <a href="<?= h(url('part', ['id' => $ch['id']])) ?>"><?= h(Domain::componentName($ch)) ?></a></td>
      <td><?= h(Catalog::slotName($ch['slot'])) ?></td><td><?= h(t('since')) ?> <?= h($ch['installed_on']) ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>

<?php if ($charges !== null): $sl = $charges['since_last']; $avg = $charges['average']; ?>
<section><h2><?= h(t('Charging')) ?></h2>
  <?php if (!$charges['charges']): ?><p class="muted"><?= h(t('No charge logged yet. Log one with Log maintenance →')) ?> <?= h(Catalog::actionName($charges['actions'][0])) ?>.</p>
  <?php else: ?>
  <p><?= h(t('Since the last charge ({date}):', ['date' => $sl['charged_on']])) ?> <strong><?= h(km($sl['km'], 1)) ?></strong>, <?= h(t('{h} h ride time, {rides} rides, {days} days.', ['h' => num($sl['hours'], 1), 'rides' => (int)$sl['rides'], 'days' => (int)$sl['days']])) ?>
    <?= $sl['rides_without_time'] ? '<span class="muted">' . h(t('({n} rides without a time)', ['n' => (int)$sl['rides_without_time']])) . '</span>' : '' ?></p>
  <?php if ($avg): ?><p class="muted"><?= h(t('On average between charges: {km}, {h} h, {days} days ({n} charges).', ['km' => km($avg['km'], 1), 'h' => num($avg['hours'], 1), 'days' => (int)$avg['days'], 'n' => (int)$avg['charges']])) ?></p><?php endif; ?>
  <details><summary><?= h(t('Every charge ({n})', ['n' => count($charges['charges'])])) ?></summary>
    <table class="list"><thead><tr><th><?= h(t('Charged')) ?></th><th><?= h(t('Until')) ?></th><th class="num"><?= h(t('Km')) ?></th><th class="num"><?= h(t('Hours')) ?></th><th class="num"><?= h(t('Rides')) ?></th><th class="num"><?= h(t('Days')) ?></th></tr></thead>
    <?php foreach ($charges['charges'] as $ch): ?>
      <tr><td><?= h($ch['charged_on']) ?></td><td><?= $ch['until'] ? h($ch['until']) : '<span class="muted">' . h(t('now')) . '</span>' ?></td><td class="num"><?= h(km($ch['km'], 1)) ?></td>
        <td class="num"><?= h(num($ch['hours'], 1)) ?></td><td class="num"><?= (int)$ch['rides'] ?></td><td class="num"><?= (int)$ch['days'] ?></td></tr>
    <?php endforeach; ?></table>
  </details>
  <?php endif; ?>
</section>
<?php endif; ?>

<?php if ($waxRows): ?>
<section><h2><?= h(t('Wax applications')) ?></h2>
  <table class="list"><thead><tr><th>#</th><th><?= h(t('Date')) ?></th><th><?= h(t('Type')) ?></th><th class="num"><?= h(t('At km')) ?></th><th class="num"><?= h(t('Ridden')) ?></th><th class="num"><?= h(t('Days')) ?></th><th></th></tr></thead>
  <?php foreach ($waxRows as $w): ?>
    <tr><td><?= (int)$w['n'] ?></td><td><?= h($w['date']) ?></td><td><?= h($w['type']) ?><?= $w['product'] ? ' <span class="muted">' . h($w['product']) . '</span>' : '' ?></td>
      <td class="num"><?= $w['at_km'] === null ? '–' : h(km($w['at_km'])) ?></td><td class="num"><?= h(km($w['ridden_km'])) ?></td><td class="num"><?= (int)$w['days_on'] ?></td>
      <td class="muted"><?= $w['active'] ? h(t('current')) . ($w['next_due'] ? ' · ' . h(t('next: {what}', ['what' => $w['next_due']])) : '') : h(t('ended by {what}', ['what' => lc((string)$w['ended_by'])])) ?></td></tr>
  <?php endforeach; ?></table>
  <?php if ($c['rotation_bike_id']): ?><p><a href="<?= h(url('chains', ['bike' => $c['rotation_bike_id']])) ?>"><?= h(t('Chain rotation')) ?></a></p><?php endif; ?>
</section>
<?php endif; ?>
<?php if ($parentsServed !== null): ?>
<?php $pt = Catalog::parentTypes($c['component_type'])[0] ?? 'part'; ?><p class="muted"><?= h(t('Has been on {n} {parts}', ['n' => count($parentsServed), 'parts' => lc(count($parentsServed) === 1 ? Catalog::typeName($pt) : Catalog::typePlural($pt))])) ?><?= $parentsServed ? ': ' . h(implode(', ', array_map([Domain::class, 'componentName'], $parentsServed))) : '' ?>.</p>
<?php endif; ?>

<?php if ($spokes): ?>
<section><h2><?= h(t('Spokes')) ?></h2>
  <p><?= h(t('{n} broken since {since}', ['n' => (int)$spokes['count'], 'since' => $spokes['since'] ? t('the last re-lace ({date})', ['date' => $spokes['since']]) : t('tracking began')])) ?>
    <?= $spokes['limit'] ? '<span class="muted">· ' . h(t('a re-lace is suggested from {n}', ['n' => (int)$spokes['limit']])) . '</span>' : '' ?> <?= $spokes['due'] ? status_badge('ATTENTION') : '' ?></p>
  <?php if ($spokes['breaks']): ?><ul><?php foreach ($spokes['breaks'] as $b): ?><li><?= h($b['entry_on']) ?> <?= h($b['text'] === 'Broken spoke' || $b['text'] === t('Broken spoke') ? '' : $b['text']) ?> <span class="muted"><?= h($b['repair_text'] ?? t('not replaced yet')) ?></span></li><?php endforeach; ?></ul><?php endif; ?>
  <?php if ($c['status'] === 'ACTIVE'): ?>
  <details><summary class="btn small"><?= h(t('Log a broken spoke')) ?></summary>
    <form method="post" action="<?= h(url('spoke', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
      <?= field('broke_on', t('Broke on'), today(), 'date', ['required' => true]) ?>
      <?= field('note', t('Note'), '', 'text', ['placeholder' => t('drive side, non-drive side...')]) ?>
      <label class="check"><input type="checkbox" name="replaced" value="1"> <?= h(t('Already replaced')) ?></label>
      <?= field('replaced_on', t('Replaced on'), today(), 'date') ?>
      <?php if ($spokeStock): ?><label><?= h(t('Spoke from')) ?><select name="source"><?= options(['' => t('Not tracked')] + array_combine(array_map(fn($s) => 'stock:' . $s['id'], $spokeStock), array_column($spokeStock, 'name')), '') ?></select></label><?php endif; ?>
      <button class="btn small"><?= h(t('Save')) ?></button>
    </form>
  </details>
  <?php endif; ?>
</section>
<?php endif; ?>

<?php if ($incidents): ?>
<details><summary><?= h(t('Incidents with this part ({n})', ['n' => count($incidents)])) ?></summary>
  <table class="list"><?php foreach ($incidents as $inc): ?>
    <tr><td><?= h($inc['on']) ?></td><td><?= h($inc['label']) ?></td><td><?= $inc['ride_id'] ? '<a href="' . h(url('ride', ['id' => $inc['ride_id']])) . '">' . h(t('ride')) . '</a>' : '' ?></td>
      <td class="muted"><?= h($inc['resolved_on'] ? t('solved {date}', ['date' => $inc['resolved_on']]) : t('open')) ?></td></tr>
  <?php endforeach; ?></table>
</details>
<?php endif; ?>

<section><h2><?= h(t('Where it has been')) ?></h2>
  <?php if (!$installs): ?><p class="muted"><?= h(t('Never installed.')) ?></p><?php endif; ?>
  <table class="list">
  <?php foreach ($installs as $i): ?>
    <tr class="<?= $i['voided_at'] ? 'voided' : '' ?>">
      <td><?= $i['bike_id'] ? h($i['bike_name']) : h(t('on {part}', ['part' => $i['parent_label']])) ?> <span class="muted"><?= h(Catalog::slotName($i['slot'])) ?></span></td>
      <td><?= h($i['installed_on']) ?> → <?= h($i['removed_on'] ?? t('now')) ?></td>
      <td class="muted"><?= h($i['removal_reason'] ?? '') ?><?= $i['voided_at'] ? h(t('Wrong record: {why}', ['why' => $i['void_reason']])) : '' ?></td>
      <td>
        <?php if (!$i['voided_at'] && $i['removed_on'] === null): ?>
          <details class="inline"><summary class="btn small"><?= h(t('Remove')) ?></summary>
            <form method="post" action="<?= h(url('inst_remove', ['id' => $i['id']])) ?>" class="row"><?= Csrf::field() ?>
              <label><?= h(t('On')) ?> <input type="date" name="removed_on" value="<?= h(today()) ?>" required></label>
              <label><?= h(t('Why')) ?> <input type="text" name="reason" placeholder="<?= h(t('worn, swapped...')) ?>"></label>
              <label><?= h(t('What happens to it')) ?><select name="outcome"><?= options(Inventory::dispositions(), Inventory::defaultOutcome($c['component_type'])) ?></select></label>
              <button class="btn small"><?= h(t('Remove')) ?></button></form>
          </details>
        <?php endif; ?>
        <?php if (!$i['voided_at']): ?>
          <details class="inline"><summary class="btn small"><?= h(t('Wrong?')) ?></summary>
            <form method="post" action="<?= h(url('inst_void', ['id' => $i['id']])) ?>" class="row"><?= Csrf::field() ?>
              <label><?= h(t('What was wrong')) ?> <input type="text" name="reason" required></label>
              <button class="btn small danger"><?= h(t('Mark as wrong')) ?></button>
              <small><?= h(t('For mistakes only. Its rides stop counting for this part. A real change is "Remove".')) ?></small></form>
          </details>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </table>
</section>

<section><h2><?= h(t('Maintenance')) ?></h2>
  <?php if (!$events): ?><p class="muted"><?= h(t('Nothing logged yet.')) ?></p><?php endif; ?>
  <table class="list">
  <?php foreach ($events as $e): ?>
    <tr class="<?= $e['voided_at'] ? 'voided' : '' ?>"><td><?= h($e['performed_on']) ?></td><td><?= h(Catalog::actionName($e['action_code'])) ?></td>
      <td><?= h($e['outcome'] ? Catalog::label($e['outcome']) : '') ?><?= $e['measurement_value'] !== null ? ' ' . h((float)$e['measurement_value'] . ' ' . $e['measurement_unit']) : '' ?>
        <?= $e['consumable_name'] ? '<span class="muted">· ' . h($e['consumable_name']) . '</span>' : '' ?>
        <?= $e['symptom'] ? '<span>· ' . h(t('symptom: {text}', ['text' => $e['symptom']])) . '</span>' : '' ?> <?= $e['work_done'] ? '<span>· ' . h(t('done: {text}', ['text' => $e['work_done']])) . '</span>' : '' ?>
        <span class="muted"><?= h($e['notes'] ?? '') ?></span>
        <?= $e['voided_at'] ? '<span class="muted">' . h(t('Wrong entry: {why}', ['why' => $e['void_reason']])) . '</span>' : '' ?></td>
      <td><?php if (!$e['voided_at']): ?><details class="inline"><summary class="btn small"><?= h(t('Wrong?')) ?></summary>
        <form method="post" action="<?= h(url('event_void', ['id' => $e['id']])) ?>" class="row"><?= Csrf::field() ?>
          <input type="text" name="reason" placeholder="<?= h(t('What was wrong')) ?>" required><button class="btn small danger"><?= h(t('Mark as wrong')) ?></button></form></details>
        <?php elseif (!str_starts_with((string)$e['void_reason'], 'undone')): ?><?= post_button('event_restore', ['id' => $e['id']], t('Restore'), 'btn small') ?><?php endif; ?></td></tr>
  <?php endforeach; ?>
  </table>
</section>

<details><summary><?= h(t('Service intervals for this part')) ?></summary>
  <table class="list">
  <?php foreach ($rules as $r): ?>
    <tr><td><?= h(t($r['name'])) ?><?= $r['component_id'] ? ' <span class="badge b-ok">' . h(t('this part only')) . '</span>' : '' ?></td>
      <td><?= h(rule_summary($r)) ?></td>
      <td><?php if ($r['component_id']): ?>
        <a class="btn small" href="<?= h(url('rule_edit', ['id' => $r['id']])) ?>"><?= h(t('Change')) ?></a>
        <?= post_button('rule_delete', ['id' => $r['id']], t('Use normal interval'), 'btn small') ?>
      <?php else: ?>
        <a class="btn small" href="<?= h(url('rule_edit', ['part' => $c['id'], 'code' => $r['rule_code']])) ?>"><?= h(t('Change for this part')) ?></a>
      <?php endif; ?></td></tr>
  <?php endforeach; ?>
  </table>
  <p><a href="<?= h(url('rules')) ?>"><?= h(t('All service intervals')) ?></a></p>
</details>

<details><summary><?= h(t('Correct the km')) ?></summary>
  <form method="post" action="<?= h(url('adjust', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <?= field('km', t('Km (+ or −)'), '', 'text', ['inputmode' => 'decimal', 'required' => true]) ?>
    <?= field('effective_on', t('On'), today(), 'date', ['required' => true]) ?>
    <?= field('note', t('Why'), '', 'text', ['required' => true]) ?>
    <label class="check"><input type="checkbox" name="is_estimate" value="1"> <?= h(t('Estimate')) ?></label>
    <button class="btn"><?= h(t('Add correction')) ?></button>
  </form>
  <table class="list"><?php foreach ($adjustments as $a): ?>
    <tr class="<?= $a['voided_at'] ? 'voided' : '' ?>"><td><?= h($a['effective_on']) ?></td><td class="num"><?= h(km((float)$a['km'], 1)) ?><?= $a['is_estimate'] ? t(' (est.)') : '' ?></td><td><?= h($a['note']) ?></td>
      <td><?= $a['voided_at'] ? '' : post_button('adjust', ['id' => $c['id']], t('Void'), 'btn small', null, ['do' => 'void', 'adj' => $a['id']]) ?></td></tr>
  <?php endforeach; ?></table>
</details>

<details><summary><?= h(t('Notes and issues ({n})', ['n' => count(array_filter($journal, fn($e) => !$e['voided_at']))])) ?></summary>
  <?= View::partial('partials/journal', ['entries' => $journal, 'bikeId' => null, 'componentId' => $c['id'], 'back' => 'r=part&id=' . $c['id']]) ?>
</details>

<?php if (!$open && $c['status'] === 'ACTIVE'): ?>
<details><summary><?= h(t('What happened to it (stored, sold, waiting for repair...)')) ?></summary>
  <form method="post" action="<?= h(url('part_status', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <input type="hidden" name="do" value="disposition">
    <label><?= h(t('Now')) ?><select name="disposition"><?= options(Inventory::dispositions(), $c['disposition']) ?></select></label>
    <?= field('on', t('Since'), today(), 'date', ['required' => true]) ?>
    <?= field('note', t('Note'), '') ?>
    <button class="btn small"><?= h(t('Save')) ?></button>
  </form>
  <?php if ($dispositions): ?><table class="list"><?php foreach ($dispositions as $d): ?>
    <tr><td><?= h($d['effective_on']) ?></td><td><?= h(Catalog::raw('dispositions')[$d['disposition']] ?? $d['disposition']) ?></td><td class="muted"><?= h($d['note'] ?? '') ?></td></tr>
  <?php endforeach; ?></table><?php endif; ?>
</details>
<?php endif; ?>

<?php if (!$order && $c['status'] === 'ACTIVE'): ?>
<details><summary><?= h(t('Send away for repair')) ?></summary>
  <form method="post" action="<?= h(url('repair_send', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <?= field('on', t('Sent on'), today(), 'date', ['required' => true]) ?>
    <?= field('shop', t('To (shop, maker)'), '', 'text', ['list' => 'shops']) ?>
    <?= field('reason', t('Why'), '') ?>
    <?php if ($incidentChoices): ?><label><?= h(t('For incident')) ?><select name="incident"><?= options($incidentChoices, '', true, t('None')) ?></select></label><?php endif; ?>
    <button class="btn small"><?= h(t('Send away')) ?></button>
  </form>
  <p class="muted"><?= h(t('It comes off the bike (with what is mounted on it) and counts no km while away.')) ?></p>
</details>
<?php endif; ?>
<?php if ($orders): ?>
<details><summary><?= h(t('Repairs ({n})', ['n' => count($orders)])) ?></summary><table class="list"><?php foreach ($orders as $o): ?>
  <tr><td><?= h($o['sent_on']) ?> → <?= h($o['returned_on'] ?? t('away')) ?></td><td><?= h($o['shop'] ?? '') ?></td>
    <td><?= $o['outcome'] ? h(t(ServiceOrders::OUTCOMES[$o['outcome']])) : '' ?><?= $o['cost_cents'] ? ' · ' . h(money((int)$o['cost_cents'])) : '' ?><?= (int)$o['replacement_id'] === (int)$c['id'] ? t(' (this part is the replacement)') : '' ?></td></tr>
<?php endforeach; ?></table></details>
<?php endif; ?>

<details><summary><?= h(t('Retire')) ?></summary>
  <?php if ($c['status'] === 'ACTIVE'): ?>
  <form method="post" action="<?= h(url('part_status', ['id' => $c['id']])) ?>" class="row"><?= Csrf::field() ?>
    <input type="hidden" name="do" value="retire">
    <?= field('retired_on', t('On'), today(), 'date', ['required' => true]) ?>
    <?= field('reason', t('Why'), '', 'text', ['placeholder' => t('worn out, crashed, sold...')]) ?>
    <button class="btn"><?= h(t('Retire part')) ?></button>
  </form>
  <p class="muted"><?= h(t('Retiring removes it from the bike on that date. History and km are kept.')) ?></p>
  <?php else: ?>
    <?= post_button('part_status', ['id' => $c['id']], t('Make active again'), 'btn', null, ['do' => 'restore']) ?>
  <?php endif; ?>
</details>
