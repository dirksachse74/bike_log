<div class="stats">
  <div><span class="big"><?= $costs['initial'] !== null ? h(money($costs['initial'])) : '–' ?></span><span class="muted"><?= $costs['initial_source'] === 'FRAME' ? 'frame (built up)' : 'bought for' ?></span></div>
  <div><span class="big"><?= h(money($costs['running'])) ?><?= $costs['estimated'] ? ' ≈' : '' ?></span><span class="muted">running cost</span></div>
  <div><span class="big"><?= h(money($costs['total'])) ?></span><span class="muted">in total</span></div>
  <div><span class="big"><?= $costs['per_km'] !== null ? h(money($costs['per_km'])) : '–' ?></span><span class="muted">per km (<?= h(km($costs['km'])) ?>)</span></div>
</div>
<p class="muted">Parts <?= h(money($costs['parts'])) ?> · bought together <?= h(money($costs['bundles'])) ?> · stock used <?= h(money($costs['stock'])) ?> (estimated) · services <?= h(money($costs['services'])) ?></p>
<?php if ($costs['initial'] === null): ?><p class="muted">No purchase price: <a href="<?= h(url('bike_edit', ['id' => $bike['id']])) ?>">add it to the bike</a>.</p><?php endif; ?>
<?php if ($costs['unpriced']): ?>
<details><summary><?= count($costs['unpriced']) ?> part(s) without a price</summary><p class="muted"><?= h(implode(', ', $costs['unpriced'])) ?></p>
  <p class="muted">Add the price on the part, or <a href="<?= h(url('bundles')) ?>">record parts bought together</a> with one price.</p></details>
<?php endif; ?>
<?php if ($costs['unpriced_bundles'] || $costs['unvalued_stock_uses']): ?><p class="muted"><?= (int)$costs['unpriced_bundles'] ?> bundle(s) without a price, <?= (int)$costs['unvalued_stock_uses'] ?> stock use(s) without a purchase price are not counted.</p><?php endif; ?>
<table class="list">
  <thead><tr><th>Date</th><th>What</th><th>Kind</th><th class="num">Amount</th></tr></thead>
  <?php foreach ($costs['items'] as $i): ?>
  <tr><td><?= h($i['date'] ?? '–') ?></td>
    <td><?= !empty($i['component_id']) ? '<a href="' . h(url('part', ['id' => $i['component_id']])) . '">' . h($i['text']) . '</a>' : h($i['text']) ?></td>
    <td class="muted"><?= h(['PART' => 'part', 'BUNDLE' => 'bought together', 'STOCK' => 'from stock', 'SERVICE' => 'service'][$i['kind']]) ?></td>
    <td class="num"><?= h(money($i['cents'])) ?><?= $i['estimated'] ? ' ≈' : '' ?></td></tr>
  <?php endforeach; ?>
</table>
<p class="muted">Each part counts for the bike it was first fitted to. A bundle counts once, for the bike most of its parts went on. Stock is valued at its average purchase price.</p>
