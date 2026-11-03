<form method="post" class="card" action="<?= h(url('my_settings')) ?>">
  <?= Csrf::field() ?>
  <h2><?= h(t('Spares to keep')) ?></h2>
  <p class="muted"><?= h(t('The shopping list suggests buying when you have fewer. Stored spare parts and counted stock both count. 0 or empty: no check.')) ?></p>
  <div class="row">
  <?php foreach ($types as $t): ?>
    <?= field('min[' . $t . ']', Catalog::typeName($t), isset($min[$t]) ? (string)$min[$t] : '', 'number', ['min' => 0, 'max' => 99]) ?>
  <?php endforeach; ?>
  </div>
  <h2><?= h(t('Wheels')) ?></h2>
  <?= field('spoke_relace_after', 'Broken spokes before a re-lace is suggested', $spokes, 'number', ['min' => 0, 'max' => 50, 'data-help' => 'Counted since the last re-lace or new spoke set. 0 turns it off.']) ?>
  <label><?= h(t('Tire setup when a wheel does not say')) ?><select name="default_tire_setup"><?= options(Catalog::raw('tire_setups'), $tire) ?></select></label>
  <button class="btn primary"><?= h(t('Save')) ?></button>
</form>
