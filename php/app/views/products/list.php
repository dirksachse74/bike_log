<p class="muted"><?= h(t('A product is what you can buy (maker, model and its specs). Your parts can point to one, so specs are typed only once.')) ?></p>
<div class="actions">
  <a class="btn primary" href="<?= h(url('product_edit', $type ? ['type' => $type] : [])) ?>"><?= h(t('+ Add product')) ?></a>
  <a class="btn" href="<?= h(url('product_import')) ?>"><?= h(t('Import JSON')) ?></a>
  <form method="get" class="row inline-form">
    <input type="hidden" name="r" value="products">
    <select name="type"><?= options(Catalog::typesByCategory(), $type, true, 'All types') ?></select>
    <button class="btn small"><?= h(t('Filter')) ?></button>
  </form>
</div>
<?php if (!$products): ?><p class="muted"><?= h(t('No products yet. Add one, import JSON files, or add a groupset (it adds its products).')) ?></p><?php endif; ?>
<table class="list">
  <thead><tr><th><?= h(t('Product')) ?></th><th><?= h(t('Type')) ?></th><th class="num"><?= h(t('List price')) ?></th><th class="num"><?= h(t('Your parts')) ?></th></tr></thead>
  <?php foreach ($products as $p): ?>
  <tr>
    <td><a href="<?= h(url('product', ['id' => $p['id']])) ?>"><?= h(Products::name($p)) ?></a></td>
    <td><?= h(Catalog::typeName($p['component_type'])) ?></td>
    <td class="num"><?= h(money($p['list_price_cents'] === null ? null : (int)$p['list_price_cents'])) ?></td>
    <td class="num"><?= (int)$p['parts'] ?></td>
  </tr>
  <?php endforeach; ?>
</table>
