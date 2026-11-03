<form method="post" class="card" action="<?= h(url('log')) ?>" data-log-form>
  <?= Csrf::field() ?>
  <script type="application/json" id="log-data"><?= json_encode(['types' => $types, 'actions' => $actionsByType, 'pre' => $preAction,
    'ui' => ['choose' => t('Choose...'), 'first' => t('Choose the part first'), 'measure' => t('From the measurement')]], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
  <label><?= h(t('Part or bike')) ?><select name="target" required data-target><?= options($targets, old('target', $selected), true, t('Choose...')) ?></select></label>
  <label><?= h(t('What was done')) ?><select name="action_code" required data-action><option value=""><?= h(t('Choose the part first')) ?></option></select></label>
  <div class="row">
    <?= field('performed_on', t('Date'), old('performed_on', today()), 'date', ['required' => true]) ?>
    <label data-outcome-wrap hidden><?= h(t('Result')) ?><select name="outcome" data-outcome></select></label>
    <label data-measure-wrap hidden><?= h(t('Measured')) ?> <span data-unit></span><input type="text" name="measurement_value" inputmode="decimal"><small><?= h(t('The result is set from the limits if you leave it empty.')) ?></small></label>
  </div>
  <div class="row">
    <label data-symptom-wrap hidden><?= h(t('Symptom')) ?><input type="text" name="symptom" maxlength="500" value="<?= h(old('symptom')) ?>" placeholder="<?= h(t('spongy lever, noise ...')) ?>"></label>
    <label data-work-wrap hidden><?= h(t('Work done')) ?><input type="text" name="work_done" maxlength="500" value="<?= h(old('work_done')) ?>" placeholder="<?= h(t('lever bleed, mineral oil ...')) ?>"></label>
  </div>
  <div class="row" data-consumable-wrap>
    <label><?= h(t('Supply used')) ?><select name="consumable_id"><?= options(array_column($consumables, 'name', 'id'), old('consumable_id'), true, t('None')) ?></select></label>
    <?= field('consumable_qty', t('Amount'), old('consumable_qty'), 'text', ['inputmode' => 'decimal', 'data-help' => t('Optional; taken from stock.')]) ?>
  </div>
  <details><summary><?= h(t('Cost, shop, notes')) ?></summary>
    <div class="row">
      <?= field('cost', t('Cost'), old('cost'), 'text', ['inputmode' => 'decimal']) ?>
      <?= field('shop', t('Done by shop'), old('shop'), 'text', ['list' => 'shops']) ?>
    </div>
    <?= field('notes', t('Notes'), old('notes'), 'textarea') ?>
  </details>
  <button class="btn primary"><?= h(t('Save')) ?></button>
</form>
