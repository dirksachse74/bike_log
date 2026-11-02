<p class="muted">Your intervals. Changing one here changes it for all parts of that type; on a part's page you can change it for that part only.</p>
<table class="list">
  <thead><tr><th>Rule</th><th>For</th><th>Interval</th><th>Source</th><th></th></tr></thead>
  <?php foreach ($rules as $r): ?>
  <tr class="<?= (int)$r['active'] ? '' : 'retired' ?>">
    <td><?= h($r['name']) ?></td>
    <td><?= $r['component_id'] ? '<a href="' . h(url('part', ['id' => $r['component_id']])) . '">' . h($r['label']) . '</a>' : h(Catalog::typeName((string)$r['component_type'])) ?>
      <?= $r['requires_setup'] ? '<span class="muted">(' . h(strtolower($r['requires_setup'])) . ' only)</span>' : '' ?></td>
    <td><?= h(rule_summary($r)) ?></td><td class="muted"><?= h(Catalog::label($r['origin'])) ?></td>
    <td><a class="btn small" href="<?= h(url('rule_edit', ['id' => $r['id']])) ?>">Change</a></td>
  </tr>
  <?php endforeach; ?>
</table>
