<form method="get" class="row inline-form"><input type="hidden" name="r" value="part_life">
  <select name="type"><?= options(Catalog::typesByCategory(), $type, true, 'All part types') ?></select><button class="btn small"><?= h(t('Show')) ?></button></form>
<p class="muted"><?= h(t('How long your parts lasted. A part is finished when it is out of use for good (retired, discarded, sold, returned under warranty). Parts still in use are listed apart and never part of an average. "≈" marks estimates (km from before tracking), "at least" an unknown earlier history.')) ?></p>
<?php if (!$types): ?><p class="muted"><?= h(t('No parts with a history yet.')) ?></p><?php endif; ?>
<?php foreach ($types as $t): ?>
<section><h2><?= h($t['name']) ?></h2>
  <?php if ($t['overall']): $o = $t['overall']; ?>
    <p><?= (int)$o['count'] ?> <?= h(t('finished: on average')) ?> <?= h(km($o['avg_km'])) ?><?= $o['estimated'] ? ' ≈' : '' ?> (<?= h(km($o['min_km'])) ?>–<?= h(km($o['max_km'])) ?>)<?= $o['avg_months'] !== null ? ', ' . h(number_format($o['avg_months'], 1)) . ' months' : '' ?><?= $o['avg_hours'] !== null ? ', ' . h(number_format($o['avg_hours'], 1)) . ' h' : '' ?></p>
    <?php if (count($t['products']) > 1 || ($t['products'][0]['product'] ?? '') !== 'No product recorded'): ?>
    <table class="list"><thead><tr><th><?= h(t('Product')) ?></th><th class="num"><?= h(t('Finished')) ?></th><th class="num"><?= h(t('Average')) ?></th><th class="num"><?= h(t('Range')) ?></th><th class="num"><?= h(t('Months')) ?></th></tr></thead>
      <?php foreach ($t['products'] as $p): ?><tr><td><?= h($p['product']) ?></td><td class="num"><?= (int)$p['count'] ?></td><td class="num"><?= h(km($p['avg_km'])) ?><?= $p['estimated'] ? ' ≈' : '' ?></td>
        <td class="num"><?= h(km($p['min_km'])) ?>–<?= h(km($p['max_km'])) ?></td><td class="num"><?= $p['avg_months'] !== null ? h(number_format($p['avg_months'], 1)) : '–' ?></td></tr><?php endforeach; ?></table>
    <?php endif; ?>
  <?php endif; ?>
  <details <?= $t['finished'] ? '' : 'open' ?>><summary><?= count($t['finished']) ?> <?= h(t('finished ·')) ?> <?= count($t['in_use']) ?> <?= h(t('still in use')) ?></summary>
    <table class="list"><thead><tr><th><?= h(t('Part')) ?></th><th><?= h(t('Bikes')) ?></th><th><?= h(t('From → to')) ?></th><th class="num"><?= h(t('Km')) ?></th><th><?= h(t('Why it went')) ?></th></tr></thead>
    <?php foreach (array_merge($t['finished'], $t['in_use']) as $r): ?>
      <tr class="<?= $r['finished'] ? '' : 'muted' ?>"><td><a href="<?= h(url('part', ['id' => $r['component']['id']])) ?>"><?= h(Domain::componentName($r['component'])) ?></a> <span class="muted"><?= h($r['product'] ?? '') ?></span></td>
        <td><?= h(implode(', ', $r['bikes'])) ?></td><td><?= h($r['first'] ?? '?') ?> → <?= h($r['ended'] ?? 'in use') ?><?= $r['months'] !== null ? ' <span class="muted">(' . h(number_format($r['months'], 1)) . ' mo)</span>' : '' ?></td>
        <td class="num"><?= $r['status'] === 'at_least' ? 'at least ' : '' ?><?= h(km($r['km'])) ?><?= $r['status'] === 'estimated' ? ' ≈' : '' ?></td><td class="muted"><?= h($r['why'] ?? '') ?></td></tr>
    <?php endforeach; ?></table>
  </details>
</section>
<?php endforeach; ?>
