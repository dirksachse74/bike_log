<form method="post" class="card" action="<?= h(url('bike_edit', ['id' => $bike['id']])) ?>">
  <?= Csrf::field() ?>
  <?= field('name', 'Name', old('name', (string)$bike['name']), 'text', ['required' => true, 'maxlength' => 120, 'data-help' => 'What you call it, e.g. "Synapse".']) ?>
  <div class="row">
    <?= field('maker', 'Maker', old('maker', (string)$bike['maker'])) ?>
    <?= field('model', 'Model', old('model', (string)$bike['model'])) ?>
    <?= field('year', 'Year', old('year', (string)$bike['year']), 'number', ['min' => 1950, 'max' => 2100]) ?>
  </div>
  <label>Shifting<select name="shifting"><?= options(['ELECTRONIC' => 'Electronic (Di2, AXS...)', 'MECHANICAL' => 'Mechanical (cables)'], old('shifting', (string)$bike['shifting']), true, 'Not set') ?></select>
    <small>Cable checks are only offered for mechanical shifting.</small></label>
  <details><summary>Purchase and notes</summary>
    <div class="row">
      <?= field('purchase_date', 'Bought on', old('purchase_date', (string)$bike['purchase_date']), 'date') ?>
      <?= field('purchase_price', 'Price paid', old('purchase_price', money($bike['purchase_price_cents'] === null ? null : (int)$bike['purchase_price_cents'])), 'text', ['inputmode' => 'decimal']) ?>
    </div>
    <?= field('notes', 'Notes', old('notes', (string)$bike['notes']), 'textarea') ?>
  </details>
  <button class="btn primary">Save</button>
  <a class="btn" href="<?= h($bike['id'] ? url('bike', ['id' => $bike['id']]) : url('bikes')) ?>">Cancel</a>
</form>
