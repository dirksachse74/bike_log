<form method="get" class="row"><input type="hidden" name="r" value="brakes">
  <label><?= h(t('Bike')) ?><select name="bike"><?= options(array_column($bikes, 'name', 'id'), $bikeId ?? '', true, t('All bikes')) ?></select></label>
  <button class="btn small"><?= h(t('Show')) ?></button></form>
<?php if (!$rows): ?><p class="muted"><?= h(t('No brake circuits yet. Add them as parts (type “Brake circuit”) or with a groupset import.')) ?></p><?php endif; ?>
<?php foreach ($rows as $r): $c = $r['component']; $b = $r['last_bleed']; ?>
<div class="card">
  <h3><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(Domain::componentName($c)) ?></a>
    <span class="muted"><?= $r['bike'] ? h($r['bike']['name']) . ($r['position'] ? ' · ' . h($r['position']) : '') : h(t('spare')) ?></span></h3>
  <p><?= h(t('Brake fluid:')) ?> <?= $r['fluid'] ? status_badge($r['fluid']['status']) . ' ' . h($r['fluid']['text']) : '<span class="muted">' . h(t('no reminder set')) . '</span>' ?></p>
  <p><?= h(t('Last fluid change:')) ?> <?= $r['last_fluid'] ? h($r['last_fluid']['performed_on']) . ($r['last_fluid']['work_done'] ? ' · ' . h($r['last_fluid']['work_done']) : '') : '<span class="muted">' . h(t('none logged')) . '</span>' ?></p>
  <p><?= h(t('Last bleed:')) ?> <?php if ($b): ?><?= h($b['performed_on']) ?><?= $b['symptom'] ? ' · ' . h(t('symptom: {text}', ['text' => $b['symptom']])) : '' ?><?= $b['work_done'] ? ' · ' . h(t('done: {text}', ['text' => $b['work_done']])) : '' ?><?= $b['outcome'] ? ' · ' . h(Catalog::label($b['outcome'])) : '' ?>
    <?php else: ?><span class="muted"><?= h(t('none logged')) ?></span><?php endif; ?></p>
  <?php if ($r['last_check']): ?><p class="muted"><?= h(t('Last check:')) ?> <?= h($r['last_check']['performed_on']) ?><?= $r['last_check']['outcome'] ? ' · ' . h(Catalog::label($r['last_check']['outcome'])) : '' ?><?= $r['last_check']['symptom'] ? ' · ' . h($r['last_check']['symptom']) : '' ?></p><?php endif; ?>
  <div class="actions">
    <a class="btn small" href="<?= h(url('log', ['part' => $c['id'], 'action' => 'BRAKE_BLEED'])) ?>"><?= h(t('Log a bleed')) ?></a>
    <a class="btn small" href="<?= h(url('log', ['part' => $c['id'], 'action' => 'BRAKE_FLUID_REPLACE'])) ?>"><?= h(t('Log a fluid change')) ?></a>
  </div>
</div>
<?php endforeach; ?>
