<div class="stats">
  <div><span class="big"><?= $costs['initial'] !== null ? h(money($costs['initial'])) : '–' ?></span><span class="muted"><?= $costs['initial_source'] === 'FRAME' ? 'frame (built up)' : 'bought for' ?></span></div>
  <div><span class="big"><?= h(money($costs['running'])) ?><?= $costs['estimated'] ? ' ≈' : '' ?></span><span class="muted"><?= h(t('running cost')) ?></span></div>
  <div><span class="big"><?= h(money($costs['total'])) ?></span><span class="muted"><?= h(t('in total')) ?></span></div>
  <div><span class="big"><?= $costs['per_km'] !== null ? h(money($costs['per_km'])) : '–' ?></span><span class="muted"><?= h(t('per km (')) ?><?= h(km($costs['km'])) ?>)</span></div>
</div>
<p class="muted"><?= h(t('Parts')) ?> <?= h(money($costs['parts'])) ?> <?= h(t('· bought together')) ?> <?= h(money($costs['bundles'])) ?> <?= h(t('· stock used')) ?> <?= h(money($costs['stock'])) ?> <?= h(t('(estimated) · services')) ?> <?= h(money($costs['services'])) ?></p>
<?php if ($costs['initial'] === null): ?><p class="muted"><?= h(t('No purchase price:')) ?> <a href="<?= h(url('bike_edit', ['id' => $bike['id']])) ?>"><?= h(t('add it to the bike')) ?></a>.</p><?php endif; ?>
<?php if ($costs['unpriced']): ?>
<details><summary><?= count($costs['unpriced']) ?> <?= h(t('part(s) without a price')) ?></summary><p class="muted"><?= h(implode(', ', $costs['unpriced'])) ?></p>
  <p class="muted"><?= h(t('Add the price on the part, or')) ?> <a href="<?= h(url('bundles')) ?>"><?= h(t('record parts bought together')) ?></a> <?= h(t('with one price.')) ?></p></details>
<?php endif; ?>
<?php if ($costs['unpriced_bundles'] || $costs['unvalued_stock_uses']): ?><p class="muted"><?= (int)$costs['unpriced_bundles'] ?> <?= h(t('bundle(s) without a price,')) ?> <?= (int)$costs['unvalued_stock_uses'] ?> <?= h(t('stock use(s) without a purchase price are not counted.')) ?></p><?php endif; ?>
<table class="list">
  <thead><tr><th><?= h(t('Date')) ?></th><th><?= h(t('What')) ?></th><th><?= h(t('Kind')) ?></th><th class="num"><?= h(t('Amount')) ?></th></tr></thead>
  <?php foreach ($costs['items'] as $i): ?>
  <tr><td><?= h($i['date'] ?? '–') ?></td>
    <td><?= !empty($i['component_id']) ? '<a href="' . h(url('part', ['id' => $i['component_id']])) . '">' . h($i['text']) . '</a>' : h($i['text']) ?></td>
    <td class="muted"><?= h(['PART' => 'part', 'BUNDLE' => 'bought together', 'STOCK' => 'from stock', 'SERVICE' => 'service'][$i['kind']]) ?></td>
    <td class="num"><?= h(money($i['cents'])) ?><?= $i['estimated'] ? ' ≈' : '' ?></td></tr>
  <?php endforeach; ?>
</table>
<p class="muted"><?= h(t('Each part counts for the bike it was first fitted to. A bundle counts once, for the bike most of its parts went on. Stock is valued at its average purchase price.')) ?></p>
