<form method="post" class="card" action="<?= h(url('part_install', ['id' => $c['id']])) ?>">
  <?= Csrf::field() ?>
  <?php if ($open): ?><p class="muted">It is installed somewhere now; installing moves it (removed there on the same date).</p><?php endif; ?>
  <label>Where does it go?
    <select name="target" required>
      <?php $opts = []; foreach ($bikes as $b) { $opts['Bikes']['b:' . $b['id']] = $b['name']; }
        foreach ($parents as $id => $label) { $opts['On a part']['p:' . $id] = $label; } ?>
      <?= options($opts, old('target'), true, 'Choose...') ?>
    </select></label>
  <label>Position<select name="slot"><?= options(array_combine(Catalog::slots($c['component_type']), array_map([Catalog::class, 'slotName'], Catalog::slots($c['component_type']))), old('slot')) ?></select></label>
  <?= field('installed_on', 'Installed on', old('installed_on', today()), 'date', ['required' => true, 'data-help' => 'Rides from this day on count for this part. If a part sits in that position, it is removed on the same day.']) ?>
  <?= field('note', 'Note', old('note')) ?>
  <button class="btn primary">Install</button>
  <a class="btn" href="<?= h(url('part', ['id' => $c['id']])) ?>">Cancel</a>
</form>
