<form method="post" class="card" action="<?= h(url('groupset')) ?>">
  <?= Csrf::field() ?>
  <input type="hidden" name="tpl" value="<?= h($code) ?>"><input type="hidden" name="picked" value="1">
  <p><strong><?= h($t['name']) ?></strong> <a class="small" href="<?= h(url('groupset', ['bike' => $bikeId])) ?>"><?= h(t('Change')) ?></a></p>
  <?php if (!$t['verified']): ?><p class="muted"><?= h(t('Specs from a template, not checked against {maker}\'s documentation yet.', ['maker' => $t['maker']])) ?></p><?php endif; ?>
  <div class="row">
    <label><?= h(t('Bike')) ?><select name="bike_id"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?: '', true, t('No bike: all as spares')) ?></select></label>
    <?= field('on', t('Fitted on'), $form['on'], 'date', ['required' => true]) ?>
  </div>
  <div class="row">
    <?php foreach ($t['options'] as $o): ?>
      <label><?= h(t($o['label'])) ?><select name="opt[<?= h($o['key']) ?>]"><?= options(t_list(array_column($o['choices'], 'label', 'value')), $opts[$o['key']]) ?></select></label>
    <?php endforeach; ?>
  </div>
  <fieldset><legend><?= h(t('If a place on the bike is taken')) ?></legend>
    <?php foreach (t_list(Groupsets::OCCUPIED) as $k => $label): ?>
      <label class="check"><input type="radio" name="occupied" value="<?= h($k) ?>" <?= $form['occupied'] === $k ? 'checked' : '' ?>> <?= h($label) ?></label>
    <?php endforeach; ?>
  </fieldset>
  <details><summary><?= h(t('Names, condition, purchase')) ?></summary>
    <div class="row">
      <?= field('prefix', t('Name prefix'), $form['prefix'], 'text', ['maxlength' => 60, 'data-help' => t('Parts are named like "{prefix} chain".', ['prefix' => $form['prefix'] ?: 'Ultegra'])]) ?>
      <label><?= h(t('Condition')) ?><select name="prior"><?= options(['NEW' => t('New'), 'UNKNOWN' => t('Used, km unknown')], $form['prior']) ?></select></label>
      <?= field('purchase_date', t('Bought on'), $form['purchase_date'], 'date') ?>
      <?= field('bundle_price', t('Bought as one, for (total)'), $form['bundle_price'], 'text', ['inputmode' => 'decimal', 'data-help' => t('Then the parts get no own price; the total counts once. Leave empty to price parts one by one.')]) ?>
      <?= field('merchant', t('Shop'), $form['merchant'], 'text', ['list' => 'shops']) ?>
    </div>
  </details>
  <button class="btn" name="do" value="preview"><?= h(t('Update preview')) ?></button>

  <?php if ($error): ?><div class="flash error"><?= h($error) ?></div><?php endif; ?>
  <?php if ($plan): ?>
  <h2><?= h(t('What will happen')) ?></h2>
  <p class="muted"><?= h(t('{installed} installed · {replace} replace a part · {spare} as spares', ['installed' => (int)$plan['counts']['INSTALL'], 'replace' => (int)$plan['counts']['REPLACE'], 'spare' => (int)$plan['counts']['SPARE']])) ?></p>
  <table class="list">
    <thead><tr><th><?= h(t('Add')) ?></th><th><?= h(t('Part')) ?></th><th><?= h(t('What happens')) ?></th><th><?= h(t('Keep as spare')) ?></th><th><?= h(t('Price')) ?></th></tr></thead>
    <?php $sel = array_column($plan['items'], 'key'); foreach ($plan['all'] as $it): $row = null; foreach ($plan['items'] as $r) { if ($r['key'] === $it['key']) { $row = $r; } } ?>
    <tr class="<?= $row ? '' : 'retired' ?>">
      <td><input type="checkbox" name="include[]" value="<?= h($it['key']) ?>" <?= $row ? 'checked' : '' ?> aria-label="<?= h(t('Add {name}', ['name' => $it['name']])) ?>"></td>
      <td><?= h($row['label'] ?? $it['name']) ?> <span class="muted"><?= h(Catalog::typeName($it['type'])) ?> · <?= h($it['model']) ?></span></td>
      <td><?= $row ? h($row['text']) : '<span class="muted">' . h(t('not added')) . '</span>' ?></td>
      <td><?php if ($bikeId): ?><input type="checkbox" name="spare[]" value="<?= h($it['key']) ?>" <?= in_array($it['key'], $spares, true) ? 'checked' : '' ?> aria-label="<?= h(t('Keep as spare')) ?>"><?php endif; ?></td>
      <td><input type="text" name="price[<?= h($it['key']) ?>]" value="<?= isset($prices[$it['key']]) && $prices[$it['key']] !== null ? h(number_format($prices[$it['key']] / 100, 2, '.', '')) : '' ?>" inputmode="decimal" size="6" aria-label="<?= h(t('Price')) ?>"></td>
    </tr>
    <?php endforeach; ?>
  </table>
  <p class="muted"><?= h(t('Change the ticks and press "Update preview" to see the result first.')) ?></p>
  <button class="btn primary" name="do" value="import"><?= h(t('Add these parts')) ?></button>
  <?php endif; ?>
</form>
