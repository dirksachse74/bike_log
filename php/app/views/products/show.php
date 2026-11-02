<p class="muted"><?= h(Catalog::typeName($p['component_type'])) ?><?= $p['list_price_cents'] !== null ? ' · list price ' . h(money((int)$p['list_price_cents'])) : '' ?></p>
<div class="actions"><a class="btn" href="<?= h(url('product_edit', ['id' => $p['id']])) ?>">Edit</a> <a class="btn" href="<?= h(url('products')) ?>">All products</a></div>

<section><h2>Specs</h2>
  <?php if (!$specs): ?><p class="muted">No specs yet. Edit the product or import a JSON file for it.</p><?php else: ?>
  <table class="list">
    <?php foreach ($specs as $k => $v): $f = $fields[$k] ?? null; ?>
    <tr><td><?= h($f ? $f['description'] : ChangeLog::fieldLabel($k)) ?></td>
      <td><?= h(is_bool($v) ? ($v ? 'yes' : 'no') : (string)$v) ?><?= $f && $f['unit'] ? ' ' . h($f['unit']) : '' ?></td></tr>
    <?php endforeach; ?>
  </table>
  <?php endif; ?>
  <p class="muted"><?= h(implode(' · ', array_filter([$p['spec_source'] ? 'Source: ' . $p['spec_source'] : null, $p['spec_version']]))) ?></p>
  <?php if ($p['notes']): ?><p><?= nl2br(h($p['notes'])) ?></p><?php endif; ?>
</section>

<section><h2>Your parts of this product</h2>
  <?php if (!$parts): ?><p class="muted">None yet.</p><?php else: ?>
  <table class="list"><?php foreach ($parts as $c): ?>
    <tr class="<?= $c['status'] === 'RETIRED' ? 'retired' : '' ?>"><td><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(Domain::componentName($c)) ?></a></td>
      <td><?= $c['status'] === 'RETIRED' ? status_badge('RETIRED') : ($c['bike'] ? h($c['bike']['name']) : '<span class="muted">spare</span>') ?></td></tr>
  <?php endforeach; ?></table>
  <?php endif; ?>
  <details><summary class="btn small">+ Add one as a spare</summary>
    <form method="post" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="spare">
      <div class="row">
        <?= field('label', 'Name', '', 'text', ['required' => true, 'maxlength' => 160, 'placeholder' => 'Spare ' . mb_strtolower(Catalog::typeName($p['component_type'])) . ' 1']) ?>
        <?= field('price', 'Price paid', '', 'text', ['inputmode' => 'decimal']) ?>
        <?= field('purchase_date', 'Bought on', '', 'date') ?>
        <?= field('shop', 'Shop', '', 'text', ['list' => 'shops']) ?>
        <?= field('storage_location', 'Stored where', '') ?>
        <label>Condition<select name="prior"><?= options(['NEW' => 'New', 'UNKNOWN' => 'Used, km unknown'], 'NEW') ?></select></label>
      </div>
      <button class="btn primary">Add spare</button>
    </form>
  </details>
</section>
