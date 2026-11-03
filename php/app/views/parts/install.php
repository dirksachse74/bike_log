<form method="post" class="card" action="<?= h(url('part_install', ['id' => $c['id']])) ?>">
  <?= Csrf::field() ?>
  <?php if ($open): ?><p class="muted"><?= h(t('It is installed somewhere now; installing moves it (removed there on the same date).')) ?></p><?php endif; ?>
  <label><?= h(t('Where does it go?')) ?>
    <select name="target" required>
      <?php $opts = []; foreach ($bikes as $b) { $opts['Bikes']['b:' . $b['id']] = $b['name']; }
        foreach ($parents as $id => $label) { $opts['On a part']['p:' . $id] = $label; } ?>
      <?= options($opts, old('target'), true, 'Choose...') ?>
    </select></label>
  <label><?= h(t('Position')) ?><select name="slot"><?= options(array_combine(Catalog::slots($c['component_type']), array_map([Catalog::class, 'slotName'], Catalog::slots($c['component_type']))), old('slot')) ?></select></label>
  <?= field('installed_on', 'Installed on', old('installed_on', today()), 'date', ['required' => true, 'data-help' => 'Rides from this day on count for this part. If a part sits in that position, it is removed on the same day.']) ?>
  <label><?= h(t('If a part sits there, it becomes')) ?><select name="old_outcome"><?= options(['' => 'The usual for that part'] + Inventory::dispositions(), old('old_outcome')) ?></select></label>
  <?= field('note', 'Note', old('note')) ?>
  <button class="btn primary"><?= h(t('Install')) ?></button>
  <a class="btn" href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(t('Cancel')) ?></a>
</form>
