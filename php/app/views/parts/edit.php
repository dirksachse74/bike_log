<?php $isNew = !$c['id']; $t = $c['component_type']; ?>
<form method="post" class="card" action="<?= h(url('part_edit', ['id' => $c['id']])) ?>" data-part-form>
  <?= Csrf::field() ?>
  <?php if ($isNew): ?>
    <label><?= h(t('Type')) ?><select name="component_type" required data-type-select><?= options(Catalog::typesByCategory(), old('component_type', $t)) ?></select></label>
  <?php else: ?>
    <p><strong><?= h(Catalog::typeName($t)) ?></strong></p>
  <?php endif; ?>
  <?= field('label', t('Name'), old('label', (string)$c['label']), 'text', ['maxlength' => 160, 'data-help' => t('Optional. Empty = maker + model, e.g. "KMC X12".')]) ?>
  <div class="row">
    <?= field('maker', t('Maker'), old('maker', (string)$c['maker'])) ?>
    <?= field('model', t('Model'), old('model', (string)$c['model'])) ?>
    <?= field('mark', t('Mark'), old('mark', (string)$c['mark']), 'text', ['maxlength' => 80, 'data-help' => t('To tell identical parts apart, e.g. "A" or "1 dot".')]) ?>
  </div>
  <fieldset>
    <legend><?= h(t('Km before you started tracking it')) ?></legend>
    <label class="check"><input type="radio" name="prior_usage" value="NEW" <?= old('prior_usage', $c['prior_usage']) === 'NEW' ? 'checked' : '' ?>> <?= h(t('New (0 km)')) ?></label>
    <label class="check"><input type="radio" name="prior_usage" value="RECORDED" <?= old('prior_usage', $c['prior_usage']) === 'RECORDED' ? 'checked' : '' ?>> <?= h(t('Used, about this many km:')) ?></label>
    <div class="row">
      <?= field('starting_km', t('Km before'), old('starting_km', (string)$c['starting_km']), 'text', ['inputmode' => 'decimal']) ?>
      <label class="check"><input type="checkbox" name="starting_km_estimate" value="1" <?= $c['starting_km_estimate'] ? 'checked' : '' ?>> <?= h(t('That is an estimate')) ?></label>
    </div>
    <label class="check"><input type="radio" name="prior_usage" value="UNKNOWN" <?= old('prior_usage', $c['prior_usage']) === 'UNKNOWN' ? 'checked' : '' ?>> <?= h(t('Unknown (km shown as "at least")')) ?></label>
  </fieldset>
  <?php if ($isNew): ?>
  <fieldset>
    <legend><?= h(t('Install it now (optional)')) ?></legend>
    <div class="row">
      <label><?= h(t('On bike')) ?><select name="install_bike_id"><?= options(array_column($bikes, 'name', 'id'), old('install_bike_id', (string)$preBike), true, t('Not now (spare)')) ?></select></label>
      <?php if ($parents): ?><label><?= h(t('or on part')) ?><select name="install_parent_id"><?= options($parents, old('install_parent_id'), true, '—') ?></select></label><?php endif; ?>
      <label><?= h(t('Position')) ?><select name="slot" data-slot-select><?= options(array_combine(Catalog::slots($t), array_map([Catalog::class, 'slotName'], Catalog::slots($t))), old('slot')) ?></select></label>
      <?= field('installed_on', t('Since'), old('installed_on', today()), 'date') ?>
    </div>
    <small><?= h(t('Parts that go on a wheel (tire, tube, cassette, rotor) can be installed on the wheel after saving. Change the type above and save first to see more positions.')) ?></small>
  </fieldset>
  <?php endif; ?>
  <details <?= in_array($t, ['FRONT_WHEEL', 'REAR_WHEEL'], true) ? 'open' : '' ?>><summary><?= h(t('More details')) ?></summary>
    <?php if ($isNew || in_array($t, ['FRONT_WHEEL', 'REAR_WHEEL', 'WHEELSET'], true)): ?>
    <label><?= h(t('Tire setup (wheels and wheelsets)')) ?><select name="tire_setup"><?= options(['TUBE' => t('Inner tubes'), 'TUBELESS' => t('Tubeless'), 'TUBULAR' => t('Tubular')], old('tire_setup', (string)$c['tire_setup']), true, t('Not set')) ?></select></label>
    <?php endif; ?>
    <div class="row">
      <?= field('purchase_date', t('Bought on'), old('purchase_date', (string)$c['purchase_date']), 'date') ?>
      <?= field('price', t('Price'), old('price', money($c['price_cents'] === null ? null : (int)$c['price_cents'])), 'text', ['inputmode' => 'decimal']) ?>
      <?= field('shop', t('Shop'), old('shop', (string)$c['shop']), 'text', ['list' => 'shops']) ?>
    </div>
    <div class="row">
      <?= field('warranty_until', t('Warranty until'), old('warranty_until', (string)($c['warranty_until'] ?? '')), 'date') ?>
      <?= field('storage_location', t('Stored where (when spare)'), old('storage_location', (string)($c['storage_location'] ?? ''))) ?>
      <?= field('pressure_note', t('Pressure note (tires)'), old('pressure_note', (string)($c['pressure_note'] ?? '')), 'text', ['placeholder' => t('e.g. 4.5 / 4.8 bar')]) ?>
    </div>
    <?= field('serial_number', t('Serial number (private)'), old('serial_number', (string)$c['serial_number'])) ?>
    <?= field('notes', t('Notes'), old('notes', (string)$c['notes']), 'textarea') ?>
  </details>
  <button class="btn primary"><?= h(t('Save')) ?></button>
  <a class="btn" href="<?= h($isNew ? url('parts') : url('part', ['id' => $c['id']])) ?>"><?= h(t('Cancel')) ?></a>
</form>
