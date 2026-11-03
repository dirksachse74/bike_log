<form method="get" class="row inline-form"><input type="hidden" name="r" value="part_life">
  <select name="type"><?= options(Catalog::typesByCategory(), $type, true, t('All part types')) ?></select><button class="btn small"><?= h(t('Show')) ?></button></form>
<p class="muted"><?= h(t('How long your parts lasted. A part is finished when it is out of use for good (retired, discarded, sold, returned under warranty). Parts still in use are listed apart and never part of an average. "≈" marks estimates (km from before tracking), "at least" an unknown earlier history.')) ?></p>
<?php if (!$types): ?><p class="muted"><?= h(t('No parts with a history yet.')) ?></p><?php endif; ?>
<?php foreach ($types as $t): ?>
<section><h2><?= h($t['name']) ?></h2>
  <?php if ($t['overall']): $o = $t['overall']; ?>
    <p><?= h(t('{n} finished: on average {km}', ['n' => (int)$o['count'], 'km' => km($o['avg_km'])])) ?><?= $o['estimated'] ? ' ≈' : '' ?> (<?= h(km($o['min_km'])) ?>–<?= h(km($o['max_km'])) ?>)<?= $o['avg_months'] !== null ? ', ' . h(t('{n} months', ['n' => num($o['avg_months'], 1)])) : '' ?><?= $o['avg_hours'] !== null ? ', ' . h(num($o['avg_hours'], 1)) . ' h' : '' ?></p>
    <?php if (count($t['products']) > 1 || ($t['products'][0]['product'] ?? '') !== t('No product recorded')): ?>
    <table class="list"><thead><tr><th><?= h(t('Product')) ?></th><th class="num"><?= h(t('Finished')) ?></th><th class="num"><?= h(t('Average')) ?></th><th class="num"><?= h(t('Range')) ?></th><th class="num"><?= h(t('Months')) ?></th></tr></thead>
      <?php foreach ($t['products'] as $p): ?><tr><td><?= h($p['product']) ?></td><td class="num"><?= (int)$p['count'] ?></td><td class="num"><?= h(km($p['avg_km'])) ?><?= $p['estimated'] ? ' ≈' : '' ?></td>
        <td class="num"><?= h(km($p['min_km'])) ?>–<?= h(km($p['max_km'])) ?></td><td class="num"><?= $p['avg_months'] !== null ? h(num($p['avg_months'], 1)) : '–' ?></td></tr><?php endforeach; ?></table>
    <?php endif; ?>
  <?php endif; ?>
  <details <?= $t['finished'] ? '' : 'open' ?>><summary><?= h(t('{finished} finished · {in_use} still in use', ['finished' => count($t['finished']), 'in_use' => count($t['in_use'])])) ?></summary>
    <table class="list"><thead><tr><th><?= h(t('Part')) ?></th><th><?= h(t('Bikes')) ?></th><th><?= h(t('From → to')) ?></th><th class="num"><?= h(t('Km')) ?></th><th><?= h(t('Why it went')) ?></th></tr></thead>
    <?php foreach (array_merge($t['finished'], $t['in_use']) as $r): ?>
      <tr class="<?= $r['finished'] ? '' : 'muted' ?>"><td><a href="<?= h(url('part', ['id' => $r['component']['id']])) ?>"><?= h(Domain::componentName($r['component'])) ?></a> <span class="muted"><?= h($r['product'] ?? '') ?></span></td>
        <td><?= h(implode(', ', $r['bikes'])) ?></td><td><?= h($r['first'] ?? '?') ?> → <?= h($r['ended'] ?? t('in use')) ?><?= $r['months'] !== null ? ' <span class="muted">(' . h(t('{n} mo', ['n' => num($r['months'], 1)])) . ')</span>' : '' ?></td>
        <td class="num"><?= h($r['status'] === 'at_least' ? t('at least {km}', ['km' => km($r['km'])]) : km($r['km'])) ?><?= $r['status'] === 'estimated' ? ' ≈' : '' ?></td><td class="muted"><?= h($r['why'] ?? '') ?></td></tr>
    <?php endforeach; ?></table>
  </details>
</section>
<?php endforeach; ?>
