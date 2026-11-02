<form method="post" class="card" action="<?= h(url('log')) ?>" data-log-form>
  <?= Csrf::field() ?>
  <script type="application/json" id="log-data"><?= json_encode(['types' => $types, 'actions' => $actionsByType, 'pre' => $preAction], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
  <label>Part or bike<select name="target" required data-target><?= options($targets, old('target', $selected), true, 'Choose...') ?></select></label>
  <label>What was done<select name="action_code" required data-action><option value="">Choose the part first</option></select></label>
  <div class="row">
    <?= field('performed_on', 'Date', old('performed_on', today()), 'date', ['required' => true]) ?>
    <label data-outcome-wrap hidden>Result<select name="outcome" data-outcome></select></label>
    <label data-measure-wrap hidden>Measured <span data-unit></span><input type="text" name="measurement_value" inputmode="decimal"><small>The result is set from the limits if you leave it empty.</small></label>
  </div>
  <div class="row" data-consumable-wrap>
    <label>Supply used<select name="consumable_id"><?= options(array_column($consumables, 'name', 'id'), old('consumable_id'), true, 'None') ?></select></label>
    <?= field('consumable_qty', 'Amount', old('consumable_qty'), 'text', ['inputmode' => 'decimal', 'data-help' => 'Optional; taken from stock.']) ?>
  </div>
  <details><summary>Cost, shop, notes</summary>
    <div class="row">
      <?= field('cost', 'Cost', old('cost'), 'text', ['inputmode' => 'decimal']) ?>
      <?= field('shop', 'Done by shop', old('shop')) ?>
    </div>
    <?= field('notes', 'Notes', old('notes'), 'textarea') ?>
  </details>
  <button class="btn primary">Save</button>
</form>
