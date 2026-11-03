<form method="post" class="card" action="<?= h(url('bike_edit', ['id' => $bike['id']])) ?>">
  <?= Csrf::field() ?>
  <?= field('name', t('Name'), old('name', (string)$bike['name']), 'text', ['required' => true, 'maxlength' => 120, 'data-help' => t('What you call it, e.g. "Synapse".')]) ?>
  <div class="row">
    <?= field('maker', t('Maker'), old('maker', (string)$bike['maker'])) ?>
    <?= field('model', t('Model'), old('model', (string)$bike['model'])) ?>
    <?= field('year', t('Year'), old('year', (string)$bike['year']), 'number', ['min' => 1950, 'max' => 2100]) ?>
  </div>
  <label><?= h(t('Shifting')) ?><select name="shifting"><?= options(['ELECTRONIC' => t('Electronic (Di2, AXS...)'), 'MECHANICAL' => t('Mechanical (cables)')], old('shifting', (string)$bike['shifting']), true, t('Not set')) ?></select>
    <small><?= h(t('Cable checks are only offered for mechanical shifting.')) ?></small></label>
  <details><summary><?= h(t('Purchase and notes')) ?></summary>
    <div class="row">
      <?= field('purchase_date', t('Bought on'), old('purchase_date', (string)$bike['purchase_date']), 'date') ?>
      <?= field('purchase_price', t('Price paid'), old('purchase_price', money($bike['purchase_price_cents'] === null ? null : (int)$bike['purchase_price_cents'])), 'text', ['inputmode' => 'decimal']) ?>
    </div>
    <?= field('notes', t('Notes'), old('notes', (string)$bike['notes']), 'textarea') ?>
  </details>
  <button class="btn primary"><?= h(t('Save')) ?></button>
  <a class="btn" href="<?= h($bike['id'] ? url('bike', ['id' => $bike['id']]) : url('bikes')) ?>"><?= h(t('Cancel')) ?></a>
</form>
