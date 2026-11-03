<?php $c = $component; $type = mb_strtolower(Catalog::typeName($c['component_type'])); $fitText = Workshop::FIT_TEXT;
$fitBadge = fn(string $f) => $f === 'VERIFIED' ? '<strong>✓ ' . h($fitText[$f]) . '</strong>' : '<span class="muted">' . h($fitText[$f]) . '</span>'; ?>
<p class="muted"><?= h(t('Now on')) ?> <?= $bike ? h($bike['name']) : 'the rider' ?>, <?= h(Catalog::slotName($installation['slot'])) ?><?= h(t(', since')) ?> <?= h($installation['installed_on']) ?>.
  <?= $product ? 'Product: ' . h(trim($product['maker'] . ' ' . $product['model'])) . '.' : '' ?></p>
<form method="post" class="card" action="<?= h(url('part_replace', ['id' => $c['id']])) ?>">
  <?= Csrf::field() ?>
  <fieldset><legend><?= h(t('What goes on instead?')) ?></legend>
    <?php $first = true; foreach ($spares as $s): ?>
      <label class="check"><input type="radio" name="source" value="spare:<?= (int)$s['id'] ?>" <?= $first ? 'checked' : '' ?>>
        <?= h(t('Spare:')) ?> <strong><?= h(Domain::componentName($s)) ?></strong> <span class="muted"><?= h(Domain::totalsLabel($s['km'])) ?><?= $s['storage_location'] ? ' · ' . h($s['storage_location']) : '' ?></span>
        · <?= $fitBadge($s['fit']) ?>
        <?= $s['mounted'] ? '<span class="muted">· has on it: ' . h(implode(', ', array_map([Domain::class, 'componentName'], $s['mounted']))) . '</span>' : '' ?></label>
    <?php $first = false; endforeach; ?>
    <?php foreach ($stock as $l): ?>
      <label class="check"><input type="radio" name="source" value="stock:<?= (int)$l['id'] ?>" <?= $first ? 'checked' : '' ?>>
        <?= h(t('One from stock:')) ?> <strong><?= h($l['name']) ?></strong> <span class="muted"><?= (int)$l['track_stock'] ? h(fmt_qty($l['level'])) . ' left' : 'stock not counted' ?></span> · <?= $fitBadge($l['fit']) ?></label>
    <?php $first = false; endforeach; ?>
    <?php if ($c['product_id']): ?>
      <label class="check"><input type="radio" name="source" value="same" <?= $first ? 'checked' : '' ?>> <?= h(t('A new one of the same product')) ?></label>
    <?php $first = false; endif; ?>
    <label class="check"><input type="radio" name="source" value="new" <?= $first ? 'checked' : '' ?>> <?= h(t('A new')) ?> <?= h($type) ?> <?= h(t('(fill in below)')) ?></label>
    <?php if (!$spares && !$stock): ?><p class="muted"><?= h(t('No spare')) ?> <?= h($type) ?> <?= h(t('and none in stock.')) ?></p><?php endif; ?>
  </fieldset>
  <details <?= !$spares && !$stock ? 'open' : '' ?>><summary><?= h(t('The new part (for “same product” or “new”)')) ?></summary>
    <div class="row">
      <?= field('new_label', 'Name', '', 'text', ['maxlength' => 160, 'placeholder' => $next_label]) ?>
      <?php if ($products): ?><label><?= h(t('Product')) ?><select name="product_id"><?= options(array_combine(array_column($products, 'id'), array_map(fn($p) => trim($p['maker'] . ' ' . $p['model']), $products)), $c['product_id'] ?? '', true, 'None') ?></select></label><?php endif; ?>
      <?= field('price', 'Price paid', '', 'text', ['inputmode' => 'decimal']) ?>
      <?= field('purchase_date', 'Bought on', '', 'date') ?>
      <?= field('shop', 'Shop', '', 'text', ['list' => 'shops']) ?>
      <label><?= h(t('Condition')) ?><select name="prior"><?= options(['NEW' => 'New', 'UNKNOWN' => 'Used, km unknown'], 'NEW') ?></select></label>
    </div>
    <p class="muted"><?= h(t('Leave the name empty for “')) ?><?= h($next_label) ?>”.</p>
  </details>
  <?php if ($children): ?>
  <fieldset><legend><?= h(t('Parts on the old')) ?> <?= h($type) ?><?= h(t(': move them to the new one?')) ?></legend>
    <?php foreach ($children as $ch): ?>
      <label class="check"><input type="checkbox" name="carry[]" value="<?= (int)$ch['id'] ?>" <?= $ch['carry'] ? 'checked' : '' ?>>
        <?= h(Catalog::typeName($ch['component_type'])) ?>: <?= h(Domain::componentName($ch)) ?> <span class="muted">(<?= h(Catalog::slotName($ch['slot'])) ?>)</span></label>
      <?= $ch['note'] ? '<p class="muted">' . h($ch['note']) . ' So it stays on the old part unless you tick it.</p>' : '' ?>
    <?php endforeach; ?>
    <p class="muted"><?= h(t('Unticked parts stay on the old')) ?> <?= h($type) ?><?= h(t('. If the spare already has a part in that position, that one stays on the old')) ?> <?= h($type) ?> <?= h(t('too.')) ?></p>
  </fieldset>
  <?php endif; ?>
  <div class="row">
    <?= field('on', 'Changed on', today(), 'date', ['required' => true, 'data-help' => 'Rides from this day on count for the new part.']) ?>
    <label><?= h(t('The old')) ?> <?= h($type) ?> <?= h(t('is now')) ?><select name="outcome"><?= options(Inventory::dispositions(), $suggested_outcome) ?></select></label>
    <?= field('reason', 'Why', '', 'text', ['maxlength' => 255, 'placeholder' => 'worn, 0.75 % stretch']) ?>
  </div>
  <button class="btn primary"><?= h(t('Replace')) ?></button>
  <a class="btn" href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(t('Cancel')) ?></a>
</form>
