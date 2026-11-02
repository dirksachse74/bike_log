<form method="post" class="card" action="<?= h(url('groupset')) ?>">
  <?= Csrf::field() ?>
  <input type="hidden" name="tpl" value="<?= h($code) ?>"><input type="hidden" name="picked" value="1">
  <p><strong><?= h($t['name']) ?></strong> <a class="small" href="<?= h(url('groupset', ['bike' => $bikeId])) ?>">Change</a></p>
  <?php if (!$t['verified']): ?><p class="muted">Specs from a template, not checked against <?= h($t['maker']) ?>'s documentation yet.</p><?php endif; ?>
  <div class="row">
    <label>Bike<select name="bike_id"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?: '', true, 'No bike: all as spares') ?></select></label>
    <?= field('on', 'Fitted on', $form['on'], 'date', ['required' => true]) ?>
  </div>
  <div class="row">
    <?php foreach ($t['options'] as $o): ?>
      <label><?= h($o['label']) ?><select name="opt[<?= h($o['key']) ?>]"><?= options(array_column($o['choices'], 'label', 'value'), $opts[$o['key']]) ?></select></label>
    <?php endforeach; ?>
  </div>
  <fieldset><legend>If a place on the bike is taken</legend>
    <?php foreach (Groupsets::OCCUPIED as $k => $label): ?>
      <label class="check"><input type="radio" name="occupied" value="<?= h($k) ?>" <?= $form['occupied'] === $k ? 'checked' : '' ?>> <?= h($label) ?></label>
    <?php endforeach; ?>
  </fieldset>
  <details><summary>Names, condition, purchase</summary>
    <div class="row">
      <?= field('prefix', 'Name prefix', $form['prefix'], 'text', ['maxlength' => 60, 'data-help' => 'Parts are named like "' . ($form['prefix'] ?: 'Ultegra') . ' chain".']) ?>
      <label>Condition<select name="prior"><?= options(['NEW' => 'New', 'UNKNOWN' => 'Used, km unknown'], $form['prior']) ?></select></label>
      <?= field('purchase_date', 'Bought on', $form['purchase_date'], 'date') ?>
      <?= field('bundle_price', 'Bought as one, for (total)', $form['bundle_price'], 'text', ['inputmode' => 'decimal', 'data-help' => 'Then the parts get no own price; the total counts once. Leave empty to price parts one by one.']) ?>
      <?= field('merchant', 'Shop', $form['merchant']) ?>
    </div>
  </details>
  <button class="btn" name="do" value="preview">Update preview</button>

  <?php if ($error): ?><div class="flash error"><?= h($error) ?></div><?php endif; ?>
  <?php if ($plan): ?>
  <h2>What will happen</h2>
  <p class="muted"><?= (int)$plan['counts']['INSTALL'] ?> installed · <?= (int)$plan['counts']['REPLACE'] ?> replace a part · <?= (int)$plan['counts']['SPARE'] ?> as spares</p>
  <table class="list">
    <thead><tr><th>Add</th><th>Part</th><th>What happens</th><th>Keep as spare</th><th>Price</th></tr></thead>
    <?php $sel = array_column($plan['items'], 'key'); foreach ($plan['all'] as $it): $row = null; foreach ($plan['items'] as $r) { if ($r['key'] === $it['key']) { $row = $r; } } ?>
    <tr class="<?= $row ? '' : 'retired' ?>">
      <td><input type="checkbox" name="include[]" value="<?= h($it['key']) ?>" <?= $row ? 'checked' : '' ?> aria-label="Add <?= h($it['name']) ?>"></td>
      <td><?= h($row['label'] ?? $it['name']) ?> <span class="muted"><?= h(Catalog::typeName($it['type'])) ?> · <?= h($it['model']) ?></span></td>
      <td><?= $row ? h($row['text']) : '<span class="muted">not added</span>' ?></td>
      <td><?php if ($bikeId): ?><input type="checkbox" name="spare[]" value="<?= h($it['key']) ?>" <?= in_array($it['key'], $spares, true) ? 'checked' : '' ?> aria-label="Keep as spare"><?php endif; ?></td>
      <td><input type="text" name="price[<?= h($it['key']) ?>]" value="<?= isset($prices[$it['key']]) && $prices[$it['key']] !== null ? h(number_format($prices[$it['key']] / 100, 2, '.', '')) : '' ?>" inputmode="decimal" size="6" aria-label="Price"></td>
    </tr>
    <?php endforeach; ?>
  </table>
  <p class="muted">Change the ticks and press "Update preview" to see the result first.</p>
  <button class="btn primary" name="do" value="import">Add these parts</button>
  <?php endif; ?>
</form>
