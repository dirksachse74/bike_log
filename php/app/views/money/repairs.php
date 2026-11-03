<?php if (!$away): ?><p class="muted"><?= h(t('Nothing is away. Send a part away from its page ("Send away for repair").')) ?></p><?php endif; ?>
<table class="list">
<?php foreach ($all as $o): ?>
  <tr><td><a href="<?= h(url('part', ['id' => $o['component_id']])) ?>"><?= h(Domain::componentName($o)) ?></a> <span class="muted"><?= h(Catalog::typeName($o['component_type'])) ?></span></td>
    <td><?= h($o['sent_on']) ?> → <?= h($o['returned_on'] ?? t('away')) ?></td><td class="muted"><?= h($o['shop'] ?? '') ?> <?= h($o['reason'] ?? '') ?></td>
    <td><?= $o['status'] === 'OUT' ? status_badge('SOON') : h(isset(ServiceOrders::OUTCOMES[$o['outcome']]) ? t(ServiceOrders::OUTCOMES[$o['outcome']]) : '') . ($o['cost_cents'] ? ' · ' . h(money((int)$o['cost_cents'])) : '') . ($o['replacement'] ? ' · ' . h(t('new: {part}', ['part' => $o['replacement']])) : '') ?></td></tr>
<?php endforeach; ?>
</table>
