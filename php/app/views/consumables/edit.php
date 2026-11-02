<form method="post" class="card" action="<?= h(url('supply_edit', ['id' => $item['id']])) ?>">
  <?= Csrf::field() ?>
  <label>Kind<select name="kind"><?= options(Catalog::CONSUMABLE_KINDS, old('kind', $item['kind'])) ?></select></label>
  <?= field('name', 'Name', old('name', (string)$item['name']), 'text', ['required' => true, 'maxlength' => 160]) ?>
  <div class="row">
    <?= field('maker', 'Maker', old('maker', (string)$item['maker'])) ?>
    <label>Unit<select name="unit"><?= options(['ml' => 'ml', 'g' => 'g', 'pcs' => 'pieces', 'l' => 'litre'], old('unit', $item['unit'])) ?></select></label>
  </div>
  <label class="check"><input type="checkbox" name="track_stock" value="1" <?= (int)$item['track_stock'] ? 'checked' : '' ?>> Track how much I have</label>
  <?php if (!$item['id']): ?>
  <div class="row">
    <?= field('initial_qty', 'I have now', old('initial_qty'), 'text', ['inputmode' => 'decimal']) ?>
    <?= field('initial_cost', 'It cost', old('initial_cost'), 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <?php endif; ?>
  <?= field('notes', 'Notes', old('notes', (string)$item['notes']), 'textarea') ?>
  <button class="btn primary">Save</button>
</form>
<?php if ($item['id']): ?>
  <?= post_button('supply_edit', ['id' => $item['id']], $item['archived_at'] ? 'Show in lists again' : 'Hide (used up, no longer bought)', 'btn', null, ['do' => $item['archived_at'] ? 'unarchive' : 'archive']) ?>
<?php endif; ?>
