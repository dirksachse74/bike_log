<div class="actions">
  <a class="btn primary" href="<?= h(url('groupset')) ?>">+ Add a groupset</a>
  <a class="btn" href="<?= h(url('supply_edit', ['mode' => 'COUNTED'])) ?>">+ Counted stock (tubes, pads ...)</a>
  <a class="btn" href="<?= h(url('my_settings')) ?>">Spares to keep</a>
</div>

<section><h2>Shopping list</h2>
  <?php if (!$shopping): ?><p class="muted">Nothing below what you want to keep.</p><?php endif; ?>
  <ul><?php foreach ($shopping as $s): ?><li><?= h($s['text']) ?><?= $s['consumable_id'] ? ' <a class="small" href="' . h(url('supply', ['id' => $s['consumable_id']])) . '">record a purchase</a>' : '' ?></li><?php endforeach; ?></ul>
  <p class="muted">Suggestions only; nothing is ordered.</p>
</section>

<section><h2>Spares on hand</h2>
  <table class="list"><?php foreach ($check as $c): ?>
    <tr><td><?= h(Catalog::typeName($c['component_type'])) ?></td><td><?= h($c['text']) ?></td><td><?= $c['low'] ? status_badge('SOON') : status_badge('OK') ?></td></tr>
  <?php endforeach; ?></table>
</section>

<section><h2>Counted stock</h2>
  <?php if (!$lines): ?><p class="muted">No counted stock yet. Use it for things you buy several of, like tubes or pad sets. Taking one out makes it a part of its own.</p><?php endif; ?>
  <table class="list"><?php foreach ($lines as $l): ?>
    <tr><td><a href="<?= h(url('supply', ['id' => $l['id']])) ?>"><?= h($l['name']) ?></a> <span class="muted"><?= h(Catalog::typeName((string)$l['component_type'])) ?></span></td>
      <td class="num"><?= h(fmt_qty($l['stock'])) ?> <?= h($l['unit']) ?><?= $l['min_stock'] !== null ? ' <span class="muted">(keep ' . h(fmt_qty((float)$l['min_stock'])) . ')</span>' : '' ?></td>
      <td><?= $l['stock'] >= 1 || !(int)$l['track_stock'] ? post_button('stock_take', ['id' => $l['id']], 'Take one out', 'btn small') : '' ?></td></tr>
  <?php endforeach; ?></table>
</section>

<section><h2>Individual spares</h2>
  <?php if (!$spares): ?><p class="muted">No stored spare parts.</p><?php endif; ?>
  <table class="list"><?php foreach ($spares as $s): ?>
    <tr><td><a href="<?= h(url('part', ['id' => $s['id']])) ?>"><?= h(Domain::componentName($s)) ?></a> <span class="muted"><?= h(Catalog::typeName($s['component_type'])) ?></span></td>
      <td class="num"><?= h(Domain::totalsLabel($s['totals'])) ?></td><td class="muted"><?= h($s['storage_location'] ?? '') ?></td>
      <td><a class="btn small" href="<?= h(url('part_install', ['id' => $s['id']])) ?>">Install</a></td></tr>
  <?php endforeach; ?></table>
</section>

<?php if ($waiting): ?>
<section><h2>Waiting for inspection or repair</h2>
  <table class="list"><?php foreach ($waiting as $s): ?>
    <tr><td><a href="<?= h(url('part', ['id' => $s['id']])) ?>"><?= h(Domain::componentName($s)) ?></a></td><td class="muted"><?= h(Catalog::typeName($s['component_type'])) ?> since <?= h($s['disposition_on'] ?? '') ?></td></tr>
  <?php endforeach; ?></table>
</section>
<?php endif; ?>

<?php if ($sessions): ?>
<details><summary>Recent steps (groupset imports, fixes) you can undo</summary>
  <table class="list"><?php foreach ($sessions as $w): ?>
    <tr class="<?= $w['undone_at'] ? 'voided' : '' ?>"><td><?= h($w['happened_on']) ?></td><td><a href="<?= h(url('ws', ['id' => $w['id']])) ?>"><?= h($w['title']) ?></a></td><td class="muted"><?= $w['undone_at'] ? 'undone' : '' ?></td></tr>
  <?php endforeach; ?></table>
</details>
<?php endif; ?>
