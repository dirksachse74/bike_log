<?php $c = $component; $type = lc(Catalog::typeName($c['component_type'])); $fitText = t_list(Workshop::FIT_TEXT);
$fitBadge = fn(string $f) => $f === 'VERIFIED' ? '<strong>✓ ' . h($fitText[$f]) . '</strong>' : '<span class="muted">' . h($fitText[$f]) . '</span>'; ?>
<p class="muted"><?= h(t('Now on {where}, {slot}, since {date}.', ['where' => $bike ? $bike['name'] : t('the rider'), 'slot' => Catalog::slotName($installation['slot']), 'date' => $installation['installed_on']])) ?>
  <?= $product ? h(t('Product:')) . ' ' . h(trim($product['maker'] . ' ' . $product['model'])) . '.' : '' ?></p>
<form method="post" class="card" action="<?= h(url('part_replace', ['id' => $c['id']])) ?>">
  <?= Csrf::field() ?>
  <fieldset><legend><?= h(t('What goes on instead?')) ?></legend>
    <?php $first = true; foreach ($spares as $s): ?>
      <label class="check"><input type="radio" name="source" value="spare:<?= (int)$s['id'] ?>" <?= $first ? 'checked' : '' ?>>
        <?= h(t('Spare:')) ?> <strong><?= h(Domain::componentName($s)) ?></strong> <span class="muted"><?= h(Domain::totalsLabel($s['km'])) ?><?= $s['storage_location'] ? ' · ' . h($s['storage_location']) : '' ?></span>
        · <?= $fitBadge($s['fit']) ?>
        <?= $s['mounted'] ? '<span class="muted">· ' . h(t('has on it: {list}', ['list' => implode(', ', array_map([Domain::class, 'componentName'], $s['mounted']))])) . '</span>' : '' ?></label>
    <?php $first = false; endforeach; ?>
    <?php foreach ($stock as $l): ?>
      <label class="check"><input type="radio" name="source" value="stock:<?= (int)$l['id'] ?>" <?= $first ? 'checked' : '' ?>>
        <?= h(t('One from stock:')) ?> <strong><?= h($l['name']) ?></strong> <span class="muted"><?= h((int)$l['track_stock'] ? t('{n} left', ['n' => fmt_qty($l['level'])]) : t('stock not counted')) ?></span> · <?= $fitBadge($l['fit']) ?></label>
    <?php $first = false; endforeach; ?>
    <?php if ($c['product_id']): ?>
      <label class="check"><input type="radio" name="source" value="same" <?= $first ? 'checked' : '' ?>> <?= h(t('A new one of the same product')) ?></label>
    <?php $first = false; endif; ?>
    <label class="check"><input type="radio" name="source" value="new" <?= $first ? 'checked' : '' ?>> <?= h(t('A new {type} (fill in below)', ['type' => $type])) ?></label>
    <?php if (!$spares && !$stock): ?><p class="muted"><?= h(t('No spare {type} and none in stock.', ['type' => $type])) ?></p><?php endif; ?>
  </fieldset>
  <details <?= !$spares && !$stock ? 'open' : '' ?>><summary><?= h(t('The new part (for “same product” or “new”)')) ?></summary>
    <div class="row">
      <?= field('new_label', t('Name'), '', 'text', ['maxlength' => 160, 'placeholder' => $next_label]) ?>
      <?php if ($products): ?><label><?= h(t('Product')) ?><select name="product_id"><?= options(array_combine(array_column($products, 'id'), array_map(fn($p) => trim($p['maker'] . ' ' . $p['model']), $products)), $c['product_id'] ?? '', true, t('None')) ?></select></label><?php endif; ?>
      <?= field('price', t('Price paid'), '', 'text', ['inputmode' => 'decimal']) ?>
      <?= field('purchase_date', t('Bought on'), '', 'date') ?>
      <?= field('shop', t('Shop'), '', 'text', ['list' => 'shops']) ?>
      <label><?= h(t('Condition')) ?><select name="prior"><?= options(['NEW' => t('New'), 'UNKNOWN' => t('Used, km unknown')], 'NEW') ?></select></label>
    </div>
    <p class="muted"><?= h(t('Leave the name empty for “{name}”.', ['name' => $next_label])) ?></p>
  </details>
  <?php if ($children): ?>
  <fieldset><legend><?= h(t('Parts on the old {type}: move them to the new one?', ['type' => $type])) ?></legend>
    <?php foreach ($children as $ch): ?>
      <label class="check"><input type="checkbox" name="carry[]" value="<?= (int)$ch['id'] ?>" <?= $ch['carry'] ? 'checked' : '' ?>>
        <?= h(Catalog::typeName($ch['component_type'])) ?>: <?= h(Domain::componentName($ch)) ?> <span class="muted">(<?= h(Catalog::slotName($ch['slot'])) ?>)</span></label>
      <?= $ch['note'] ? '<p class="muted">' . h($ch['note']) . ' ' . h(t('So it stays on the old part unless you tick it.')) . '</p>' : '' ?>
    <?php endforeach; ?>
    <p class="muted"><?= h(t('Unticked parts stay on the old {type}. If the spare already has a part in that position, that one stays on the old {type} too.', ['type' => $type])) ?></p>
  </fieldset>
  <?php endif; ?>
  <div class="row">
    <?= field('on', t('Changed on'), today(), 'date', ['required' => true, 'data-help' => t('Rides from this day on count for the new part.')]) ?>
    <label><?= h(t('The old {type} is now', ['type' => $type])) ?><select name="outcome"><?= options(Inventory::dispositions(), $suggested_outcome) ?></select></label>
    <?= field('reason', t('Why'), '', 'text', ['maxlength' => 255, 'placeholder' => t('worn, 0.75 % stretch')]) ?>
  </div>
  <button class="btn primary"><?= h(t('Replace')) ?></button>
  <a class="btn" href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(t('Cancel')) ?></a>
</form>
