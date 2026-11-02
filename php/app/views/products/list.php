<p class="muted">A product is what you can buy (maker, model and its specs). Your parts can point to one, so specs are typed only once.</p>
<div class="actions">
  <a class="btn primary" href="<?= h(url('product_edit', $type ? ['type' => $type] : [])) ?>">+ Add product</a>
  <a class="btn" href="<?= h(url('product_import')) ?>">Import JSON</a>
  <form method="get" class="row inline-form">
    <input type="hidden" name="r" value="products">
    <select name="type"><?= options(Catalog::typesByCategory(), $type, true, 'All types') ?></select>
    <button class="btn small">Filter</button>
  </form>
</div>
<?php if (!$products): ?><p class="muted">No products yet. Add one, import JSON files, or add a groupset (it adds its products).</p><?php endif; ?>
<table class="list">
  <thead><tr><th>Product</th><th>Type</th><th class="num">List price</th><th class="num">Your parts</th></tr></thead>
  <?php foreach ($products as $p): ?>
  <tr>
    <td><a href="<?= h(url('product', ['id' => $p['id']])) ?>"><?= h(Products::name($p)) ?></a></td>
    <td><?= h(Catalog::typeName($p['component_type'])) ?></td>
    <td class="num"><?= h(money($p['list_price_cents'] === null ? null : (int)$p['list_price_cents'])) ?></td>
    <td class="num"><?= (int)$p['parts'] ?></td>
  </tr>
  <?php endforeach; ?>
</table>
