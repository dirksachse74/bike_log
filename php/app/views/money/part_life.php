<form method="get" class="row inline-form"><input type="hidden" name="r" value="part_life">
  <select name="type"><?= options(Catalog::typesByCategory(), $type, true, 'All part types') ?></select><button class="btn small">Show</button></form>
<p class="muted">How long your parts lasted. A part is finished when it is out of use for good (retired, discarded, sold, returned under warranty). Parts still in use are listed apart and never part of an average. "≈" marks estimates (km from before tracking), "at least" an unknown earlier history.</p>
<?php if (!$types): ?><p class="muted">No parts with a history yet.</p><?php endif; ?>
<?php foreach ($types as $t): ?>
<section><h2><?= h($t['name']) ?></h2>
  <?php if ($t['overall']): $o = $t['overall']; ?>
    <p><?= (int)$o['count'] ?> finished: on average <?= h(km($o['avg_km'])) ?><?= $o['estimated'] ? ' ≈' : '' ?> (<?= h(km($o['min_km'])) ?>–<?= h(km($o['max_km'])) ?>)<?= $o['avg_months'] !== null ? ', ' . h(number_format($o['avg_months'], 1)) . ' months' : '' ?><?= $o['avg_hours'] !== null ? ', ' . h(number_format($o['avg_hours'], 1)) . ' h' : '' ?></p>
    <?php if (count($t['products']) > 1 || ($t['products'][0]['product'] ?? '') !== 'No product recorded'): ?>
    <table class="list"><thead><tr><th>Product</th><th class="num">Finished</th><th class="num">Average</th><th class="num">Range</th><th class="num">Months</th></tr></thead>
      <?php foreach ($t['products'] as $p): ?><tr><td><?= h($p['product']) ?></td><td class="num"><?= (int)$p['count'] ?></td><td class="num"><?= h(km($p['avg_km'])) ?><?= $p['estimated'] ? ' ≈' : '' ?></td>
        <td class="num"><?= h(km($p['min_km'])) ?>–<?= h(km($p['max_km'])) ?></td><td class="num"><?= $p['avg_months'] !== null ? h(number_format($p['avg_months'], 1)) : '–' ?></td></tr><?php endforeach; ?></table>
    <?php endif; ?>
  <?php endif; ?>
  <details <?= $t['finished'] ? '' : 'open' ?>><summary><?= count($t['finished']) ?> finished · <?= count($t['in_use']) ?> still in use</summary>
    <table class="list"><thead><tr><th>Part</th><th>Bikes</th><th>From → to</th><th class="num">Km</th><th>Why it went</th></tr></thead>
    <?php foreach (array_merge($t['finished'], $t['in_use']) as $r): ?>
      <tr class="<?= $r['finished'] ? '' : 'muted' ?>"><td><a href="<?= h(url('part', ['id' => $r['component']['id']])) ?>"><?= h(Domain::componentName($r['component'])) ?></a> <span class="muted"><?= h($r['product'] ?? '') ?></span></td>
        <td><?= h(implode(', ', $r['bikes'])) ?></td><td><?= h($r['first'] ?? '?') ?> → <?= h($r['ended'] ?? 'in use') ?><?= $r['months'] !== null ? ' <span class="muted">(' . h(number_format($r['months'], 1)) . ' mo)</span>' : '' ?></td>
        <td class="num"><?= $r['status'] === 'at_least' ? 'at least ' : '' ?><?= h(km($r['km'])) ?><?= $r['status'] === 'estimated' ? ' ≈' : '' ?></td><td class="muted"><?= h($r['why'] ?? '') ?></td></tr>
    <?php endforeach; ?></table>
  </details>
</section>
<?php endforeach; ?>
