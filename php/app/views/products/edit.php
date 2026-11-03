<form method="post" class="card"><?= Csrf::field() ?>
  <div class="row">
    <label><?= h(t('Part type')) ?><select name="component_type" required><?= options(Catalog::typesByCategory(), old('component_type', (string)$p['component_type']), true, 'Choose…') ?></select></label>
    <?= field('maker', 'Maker', old('maker', (string)$p['maker']), 'text', ['maxlength' => 120, 'placeholder' => 'Shimano']) ?>
    <?= field('model', 'Model', old('model', (string)$p['model']), 'text', ['required' => true, 'maxlength' => 200, 'placeholder' => 'CN-M8100']) ?>
    <?= field('list_price', 'List price (€)', old('list_price', $p['list_price_cents'] !== null ? money((int)$p['list_price_cents']) : ''), 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <?= field('specs', 'Specs, one per line as “key: value”', old('specs', $specText), 'textarea', ['rows' => 8, 'placeholder' => "speeds: 12\nlinks: 126",
      'data-help' => 'Known keys for the type are checked (see the template on the import page); other keys are kept as text.']) ?>
  <?= field('spec_source', 'Source (web page)', old('spec_source', (string)$p['spec_source']), 'text', ['maxlength' => 500]) ?>
  <?= field('notes', 'Notes', old('notes', (string)$p['notes']), 'textarea', ['rows' => 3]) ?>
  <button class="btn primary"><?= h(t('Save')) ?></button>
  <a class="btn" href="<?= h($id ? url('product', ['id' => $id]) : url('products')) ?>"><?= h(t('Cancel')) ?></a>
</form>
