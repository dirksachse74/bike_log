<form method="post" class="card" action="<?= h(url('rule_edit', $rule['id'] ? ['id' => $rule['id']] : ['part' => $rule['component_id'], 'code' => $rule['rule_code']])) ?>">
  <?= Csrf::field() ?>
  <p><strong><?= h(t($rule['name'])) ?></strong> · <?= h(t('logged as "{action}"', ['action' => Catalog::actionName($rule['action_code'])])) ?>
    <?= $rule['component_id'] ? '<br><span class="badge b-ok">' . h(t('only for this part')) . '</span>' : '' ?></p>
  <?php if ($rule['trigger_kind'] === 'ONCE_AFTER_INSTALL'): ?><p class="muted"><?= h(t('Due once after the part is fitted.')) ?></p><?php endif; ?>
  <?php if ($rule['trigger_kind'] === 'CYCLE_WINDOW'): ?>
  <p class="muted"><?= h(t('Once per cycle, inside a km window after the {action}. A wet ride asks for it at once.', ['action' => lc(Catalog::actionName((string)$rule['cycle_action_code']))])) ?></p>
  <div class="row">
    <?= field('window_min_km', t('From ... km'), (string)$rule['window_min_km'], 'text', ['inputmode' => 'decimal', 'required' => true]) ?>
    <?= field('window_max_km', t('To ... km'), (string)$rule['window_max_km'], 'text', ['inputmode' => 'decimal', 'required' => true]) ?>
    <?= field('warn_km', t('Warn ... km before'), (string)$rule['warn_km'], 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <?php elseif ($rule['trigger_kind'] === 'PARENT_COUNT'): ?>
  <?= field('interval_count', t('Replace after ... {parts}', ['parts' => lc(Catalog::typePlural(Catalog::parentTypes((string)($rule['component_type'] ?? 'QUICK_LINK'))[0] ?? 'CHAIN'))]), (string)$rule['interval_count'], 'number', ['min' => 1, 'max' => 50, 'required' => true]) ?>
  <?php else: ?>
  <div class="row">
    <?= field('interval_km', t('Every ... km'), (string)$rule['interval_km'], 'text', ['inputmode' => 'decimal']) ?>
    <?= field('warn_km', t('Warn ... km before'), (string)$rule['warn_km'], 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <div class="row">
    <?= field('interval_months', t('Every ... months'), (string)$rule['interval_months'], 'number', ['min' => 1, 'max' => 120]) ?>
    <?= field('warn_days', t('Warn ... days before'), (string)$rule['warn_days'], 'number', ['min' => 0]) ?>
  </div>
  <div class="row">
    <?= field('interval_hours', t('Every ... hours ride time'), (string)$rule['interval_hours'], 'text', ['inputmode' => 'decimal']) ?>
    <?= field('warn_hours', t('Warn ... hours before'), (string)$rule['warn_hours'], 'text', ['inputmode' => 'decimal']) ?>
  </div>
  <?php if ($rule['action_code'] === 'WAX_HOT'): ?>
    <?= field('after_top_up_km', t('After a liquid-wax top-up, hot wax ... km later'), (string)$rule['after_top_up_km'], 'text', ['inputmode' => 'decimal', 'data-help' => t('Top-up at 70 km and 200 here: hot wax due at 270 km. Empty: always the interval above.')]) ?>
  <?php endif; ?>
  <?php endif; ?>
  <label><?= h(t('Where the number comes from')) ?><select name="origin"><?= options(['MANUFACTURER' => t('Manufacturer'), 'PERSONAL' => t('My own value'), 'DEFAULT' => t('App default')], $rule['origin']) ?></select></label>
  <label class="check"><input type="checkbox" name="active" value="1" <?= (int)$rule['active'] ? 'checked' : '' ?>> <?= h(t('Remind me')) ?></label>
  <?= field('notes', t('Notes'), (string)$rule['notes'], 'textarea') ?>
  <button class="btn primary"><?= h(t('Save')) ?></button>
</form>
