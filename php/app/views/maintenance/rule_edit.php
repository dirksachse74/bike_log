<form method="post" class="card" action="<?= h(url('rule_edit', $rule['id'] ? ['id' => $rule['id']] : ['part' => $rule['component_id'], 'code' => $rule['rule_code']])) ?>">
  <?= Csrf::field() ?>
  <p><strong><?= h($rule['name']) ?></strong> · logged as "<?= h(Catalog::actionName($rule['action_code'])) ?>"
    <?= $rule['component_id'] ? '<br><span class="badge b-ok">only for this part</span>' : '' ?></p>
  <?php if ($rule['trigger_kind'] === 'ONCE_AFTER_INSTALL'): ?><p class="muted">Due once after the part is fitted.</p><?php endif; ?>
  <div class="row">
    <?= field('interval_km', 'Every ... km', (string)$rule['interval_km'], 'text', ['inputmode' => 'decimal']) ?>
    <?= field('warn_km', 'Warn ... km before', (string)$rule['warn_km'], 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <div class="row">
    <?= field('interval_months', 'Every ... months', (string)$rule['interval_months'], 'number', ['min' => 1, 'max' => 120]) ?>
    <?= field('warn_days', 'Warn ... days before', (string)$rule['warn_days'], 'number', ['min' => 0]) ?>
  </div>
  <div class="row">
    <?= field('interval_hours', 'Every ... hours ride time', (string)$rule['interval_hours'], 'text', ['inputmode' => 'decimal']) ?>
    <?= field('warn_hours', 'Warn ... hours before', (string)$rule['warn_hours'], 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <label>Where the number comes from<select name="origin"><?= options(['MANUFACTURER' => 'Manufacturer', 'PERSONAL' => 'My own value', 'DEFAULT' => 'App default'], $rule['origin']) ?></select></label>
  <label class="check"><input type="checkbox" name="active" value="1" <?= (int)$rule['active'] ? 'checked' : '' ?>> Remind me</label>
  <?= field('notes', 'Notes', (string)$rule['notes'], 'textarea') ?>
  <button class="btn primary">Save</button>
</form>
