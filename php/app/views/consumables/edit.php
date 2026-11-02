<form method="post" class="card" action="<?= h(url('supply_edit', ['id' => $item['id']])) ?>">
  <?= Csrf::field() ?>
  <?php $counted = ($item['tracking_mode'] ?? 'BULK') === 'COUNTED'; ?>
  <input type="hidden" name="tracking_mode" value="<?= $counted ? 'COUNTED' : 'BULK' ?>">
  <?php if ($counted): ?>
    <p class="muted">Counted stock: spare parts you keep several of. Taking one out (Spares page) makes it a part of its own.</p>
    <label>What kind of part<select name="component_type" required><?php $u = []; foreach (Catalog::raw('stock_units') as $t => [$unit, $help]) { $u[$t] = Catalog::typeName($t) . ' (' . $help . ')'; } ?><?= options($u, old('component_type', (string)$item['component_type']), true, 'Choose...') ?></select></label>
  <?php else: ?>
  <label>Kind<select name="kind"><?= options(Catalog::CONSUMABLE_KINDS, old('kind', $item['kind'])) ?></select></label>
  <?php endif; ?>
  <?= field('name', 'Name', old('name', (string)$item['name']), 'text', ['required' => true, 'maxlength' => 160]) ?>
  <div class="row">
    <?= field('maker', 'Maker', old('maker', (string)$item['maker'])) ?>
    <?php if (!$counted): ?><label>Unit<select name="unit"><?= options(['ml' => 'ml', 'g' => 'g', 'pcs' => 'pieces', 'l' => 'litre'], old('unit', $item['unit'])) ?></select></label><?php endif; ?>
  </div>
  <div class="row">
    <?= field('min_stock', 'Keep at least', old('min_stock', $item['min_stock'] === null ? '' : fmt_qty((float)$item['min_stock'])), 'text', ['inputmode' => 'decimal', 'data-help' => 'Below this, it goes on the shopping list.']) ?>
    <?= field('storage_location', 'Stored where', old('storage_location', (string)($item['storage_location'] ?? ''))) ?>
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
