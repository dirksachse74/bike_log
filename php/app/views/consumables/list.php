<div class="actions"><a class="btn primary" href="<?= h(url('supply_edit')) ?>"><?= h(t('+ Add supply')) ?></a>
  <a class="btn" href="<?= h(url('supply_edit', ['mode' => 'COUNTED'])) ?>"><?= h(t('+ Counted spare parts')) ?></a>
  <a class="btn" href="<?= h(url('spares')) ?>"><?= h(t('Spares and shopping list')) ?></a></div>
<p class="muted"><?= h(t('Wax, lube, sealant, brake fluid, grease... Buying and using are separate entries; stock is their sum.')) ?></p>
<table class="list">
  <thead><tr><th><?= h(t('Supply')) ?></th><th><?= h(t('Kind')) ?></th><th class="num"><?= h(t('Stock')) ?></th><th><?= h(t('Last used')) ?></th></tr></thead>
  <?php foreach ($items as $i): ?>
  <tr class="<?= $i['archived_at'] ? 'retired' : '' ?>">
    <td><a href="<?= h(url('supply', ['id' => $i['id']])) ?>"><?= h($i['name']) ?></a> <span class="muted"><?= h($i['maker'] ?? '') ?></span></td>
    <td><?= $i['tracking_mode'] === 'COUNTED' ? h(Catalog::typeName((string)$i['component_type'])) . ' <span class="muted">counted</span>' : h(Catalog::CONSUMABLE_KINDS[$i['kind']] ?? $i['kind']) ?></td>
    <td class="num"><?= (int)$i['track_stock'] ? h(rtrim(rtrim(number_format($i['stock'], 2, '.', ''), '0'), '.') . ' ' . $i['unit']) : '<span class="muted">not tracked</span>' ?></td>
    <td><?= h($i['last_used'] ?? '–') ?></td>
  </tr>
  <?php endforeach; ?>
</table>
