<p class="muted"><?= h(Catalog::CONSUMABLE_KINDS[$item['kind']] ?? $item['kind']) ?> <?= h($item['maker'] ?? '') ?></p>
<div class="stats"><div><span class="big"><?= h(rtrim(rtrim(number_format($stock, 2, '.', ''), '0'), '.') . ' ' . $item['unit']) ?></span><span class="muted"><?= h(t('in stock')) ?></span></div></div>
<div class="actions"><a class="btn" href="<?= h(url('supply_edit', ['id' => $item['id']])) ?>"><?= h(t('Edit')) ?></a></div>
<form method="post" class="card row" action="<?= h(url('supply', ['id' => $item['id']])) ?>">
  <?= Csrf::field() ?>
  <label><?= h(t('Entry')) ?><select name="kind"><?= options(['BUY' => 'Bought', 'USE' => 'Used', 'ADJUST' => 'Correction (+/−)'], 'BUY') ?></select></label>
  <?= field('qty', 'Amount (' . $item['unit'] . ')', '', 'text', ['inputmode' => 'decimal', 'required' => true]) ?>
  <?= field('happened_on', 'Date', today(), 'date', ['required' => true]) ?>
  <?= field('cost', 'Cost', '', 'text', ['inputmode' => 'decimal']) ?>
  <?= field('note', 'Note', '') ?>
  <button class="btn primary"><?= h(t('Add')) ?></button>
</form>
<table class="list">
  <?php foreach ($txns as $t): ?>
  <tr class="<?= $t['voided_at'] ? 'voided' : '' ?>"><td><?= h($t['happened_on']) ?></td><td><?= h(['BUY' => 'Bought', 'USE' => 'Used', 'ADJUST' => 'Correction'][$t['kind']]) ?></td>
    <td class="num"><?= h(($t['kind'] === 'USE' ? '−' : '+') . (float)$t['qty'] . ' ' . $item['unit']) ?></td><td class="num"><?= h(money($t['cost_cents'] === null ? null : (int)$t['cost_cents'])) ?></td>
    <td class="muted"><?= $t['maintenance_event_id'] ? 'from maintenance' : h($t['note'] ?? '') ?></td>
    <td><?= !$t['voided_at'] && !$t['maintenance_event_id'] ? post_button('supply', ['id' => $item['id']], 'Void', 'btn small', null, ['do' => 'void', 'txn' => $t['id']]) : '' ?></td></tr>
  <?php endforeach; ?>
</table>
