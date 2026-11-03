<p class="muted"><?= h($ws['happened_on']) ?><?= $ws['undone_at'] ? ' · ' . status_badge('RETIRED') . ' undone on ' . h(substr($ws['undone_at'], 0, 10)) : '' ?></p>
<?php if (!$ws['undone_at']): ?>
  <?= post_button('ws_undo', ['id' => $ws['id']], 'Undo this whole step', 'btn danger', 'Undo everything this step did? Parts it added disappear and replaced parts go back.') ?>
<?php endif; ?>
<?php if ($created): ?>
<section><h2><?= h(t('Parts it added')) ?></h2>
  <table class="list"><?php foreach ($created as $c): ?>
    <tr><td><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(Domain::componentName($c)) ?></a></td><td class="muted"><?= h(Catalog::typeName($c['component_type'])) ?> <?= h($c['model'] ?? '') ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>
<?php if ($installs): ?>
<section><h2><?= h(t('Changes on bikes and parts')) ?></h2>
  <table class="list"><?php foreach ($installs as $i): ?>
    <tr class="<?= $i['voided_at'] ? 'voided' : '' ?>"><td><a href="<?= h(url('part', ['id' => $i['component_id']])) ?>"><?= h(Domain::componentName($i)) ?></a></td>
      <td><?= $i['bike_id'] ? h($i['bike_name']) : 'on ' . h($i['parent_label']) ?> <span class="muted"><?= h(Catalog::slotName($i['slot'])) ?></span></td>
      <td><?= h($i['installed_on']) ?> → <?= h($i['removed_on'] ?? 'now') ?></td>
      <td class="muted"><?= $i['removal_outcome'] ? h(Inventory::dispositions()[$i['removal_outcome']] ?? Catalog::label($i['removal_outcome'])) : '' ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>
<p><a href="<?= h(url('spares')) ?>"><?= h(t('Spares and recent steps')) ?></a></p>
