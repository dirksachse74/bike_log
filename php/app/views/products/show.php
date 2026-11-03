<p class="muted"><?= h(Catalog::typeName($p['component_type'])) ?><?= $p['list_price_cents'] !== null ? ' · ' . h(t('list price {price}', ['price' => money((int)$p['list_price_cents'])])) : '' ?></p>
<div class="actions"><a class="btn" href="<?= h(url('product_edit', ['id' => $p['id']])) ?>"><?= h(t('Edit')) ?></a> <a class="btn" href="<?= h(url('products')) ?>"><?= h(t('All products')) ?></a></div>

<section><h2><?= h(t('Specs')) ?></h2>
  <?php if (!$specs): ?><p class="muted"><?= h(t('No specs yet. Edit the product or import a JSON file for it.')) ?></p><?php else: ?>
  <table class="list">
    <?php foreach ($specs as $k => $v): $f = $fields[$k] ?? null; ?>
    <tr><td><?= h($f ? $f['description'] : ChangeLog::fieldLabel($k)) ?></td>
      <td><?= h(is_bool($v) ? ($v ? t('yes') : t('no')) : (string)$v) ?><?= $f && $f['unit'] ? ' ' . h($f['unit']) : '' ?></td></tr>
    <?php endforeach; ?>
  </table>
  <?php endif; ?>
  <p class="muted"><?= h(implode(' · ', array_filter([$p['spec_source'] ? t('Source: {src}', ['src' => $p['spec_source']]) : null, $p['spec_version']]))) ?></p>
  <?php if ($p['notes']): ?><p><?= nl2br(h($p['notes'])) ?></p><?php endif; ?>
</section>

<section><h2><?= h(t('Your parts of this product')) ?></h2>
  <?php if (!$parts): ?><p class="muted"><?= h(t('None yet.')) ?></p><?php else: ?>
  <table class="list"><?php foreach ($parts as $c): ?>
    <tr class="<?= $c['status'] === 'RETIRED' ? 'retired' : '' ?>"><td><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(Domain::componentName($c)) ?></a></td>
      <td><?= $c['status'] === 'RETIRED' ? status_badge('RETIRED') : ($c['bike'] ? h($c['bike']['name']) : '<span class="muted">' . h(t('spare')) . '</span>') ?></td></tr>
  <?php endforeach; ?></table>
  <?php endif; ?>
  <details><summary class="btn small"><?= h(t('+ Add one as a spare')) ?></summary>
    <form method="post" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="spare">
      <div class="row">
        <?= field('label', t('Name'), '', 'text', ['required' => true, 'maxlength' => 160, 'placeholder' => t('Spare {type} 1', ['type' => lc(Catalog::typeName($p['component_type']))])]) ?>
        <?= field('price', t('Price paid'), '', 'text', ['inputmode' => 'decimal']) ?>
        <?= field('purchase_date', t('Bought on'), '', 'date') ?>
        <?= field('shop', t('Shop'), '', 'text', ['list' => 'shops']) ?>
        <?= field('storage_location', t('Stored where'), '') ?>
        <label><?= h(t('Condition')) ?><select name="prior"><?= options(['NEW' => t('New'), 'UNKNOWN' => t('Used, km unknown')], 'NEW') ?></select></label>
      </div>
      <button class="btn primary"><?= h(t('Add spare')) ?></button>
    </form>
  </details>
</section>

<section><h2><?= h(t('Fits these bikes')) ?></h2>
  <?php if (!$fits): ?><p class="muted"><?= h(t('Nothing noted yet. Note which bikes it fits, so the Replace form can tell you.')) ?></p><?php else: ?>
  <table class="list"><?php foreach ($fits as $f): ?>
    <tr><td><?= h($f['bike']) ?></td><td><?= (int)$f['verified'] ? status_badge('OK') . ' ' . h(t('checked')) : '<span class="muted">' . h(t('should fit, not checked')) . '</span>' ?></td>
      <td class="muted"><?= h($f['note'] ?? '') ?></td>
      <td><?= post_button('product', ['id' => $p['id']], t('Remove'), 'btn small', null, ['do' => 'unfit', 'bike_id' => $f['bike_id']]) ?></td></tr>
  <?php endforeach; ?></table>
  <?php endif; ?>
  <?php if ($bikes): ?>
  <details><summary class="btn small"><?= h(t('+ Note a bike it fits')) ?></summary>
    <form method="post" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="fit">
      <div class="row">
        <label><?= h(t('Bike')) ?><select name="bike_id" required><?= options(array_column($bikes, 'name', 'id'), '') ?></select></label>
        <label><?= h(t('How sure')) ?><select name="verified"><?= options(['1' => t('Checked: it fits'), '0' => t('Should fit, not checked yet')], '1') ?></select></label>
        <?= field('note', t('Note'), '', 'text', ['maxlength' => 255, 'placeholder' => t('e.g. needs the 12 mm thru-axle adapter')]) ?>
      </div>
      <button class="btn primary"><?= h(t('Save')) ?></button>
    </form>
  </details>
  <?php endif; ?>
</section>
