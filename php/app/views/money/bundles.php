<p class="muted"><?= h(t('Parts bought together at one price (a groupset, a wheelset with tires). The bundle price is the only price: its parts have none of their own, so nothing counts twice.')) ?></p>
<div class="actions"><a class="btn small" href="<?= h(url('bundles', ['show' => $show === 'all' ? '' : 'all'])) ?>"><?= $show === 'all' ? t('Hide voided') : t('Show voided') ?></a></div>
<?php foreach ($bundles as $b): ?>
<div class="card <?= $b['voided_at'] ? 'voided' : '' ?>">
  <p><strong><?= h($b['name']) ?></strong> · <?= $b['price_cents'] !== null ? h(money((int)$b['price_cents'])) : h(t('no price')) ?>
    <span class="muted"><?= h(implode(' · ', array_filter([$b['merchant'], $b['purchased_on'], $b['bike'] ? t('counts for {bike}', ['bike' => $b['bike']]) : null]))) ?> · <?= h(t('{n} of {total} in use', ['n' => (int)$b['in_use'], 'total' => count($b['members'])])) ?></span>
    <?= $b['voided_at'] ? ' · ' . h(t('voided: {why}', ['why' => $b['void_reason']])) : '' ?></p>
  <table class="list"><?php foreach ($b['members'] as $c): ?>
    <tr><td><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h(Domain::componentName($c)) ?></a> <span class="muted"><?= h(Catalog::typeName($c['component_type'])) ?></span></td>
      <td class="num muted"><?= isset($b['shares'][(int)$c['id']]) ? '≈ ' . h(money($b['shares'][(int)$c['id']])) : '' ?></td>
      <td><?= $b['voided_at'] ? '' : post_button('bundle_do', [], t('Not in it'), 'btn small link', t('Only for a part added by mistake. Take it out?'), ['do' => 'remove', 'id' => $b['id'], 'part' => $c['id']]) ?></td></tr>
  <?php endforeach; ?></table>
  <?php if (!$b['voided_at']): ?>
  <details><summary class="btn small"><?= h(t('Wrong bundle?')) ?></summary>
    <form method="post" action="<?= h(url('bundle_do')) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="void"><input type="hidden" name="id" value="<?= (int)$b['id'] ?>">
      <?= field('reason', t('What was wrong'), '', 'text', ['required' => true]) ?><button class="btn small danger"><?= h(t('Void')) ?></button></form>
  </details>
  <?php endif; ?>
</div>
<?php endforeach; ?>

<section><h2><?= h(t('Record parts bought together')) ?></h2>
  <?php if (!$candidates): ?><p class="muted"><?= h(t('Every part has its own price or a bundle already.')) ?></p><?php else: ?>
  <form method="post" action="<?= h(url('bundle_do')) ?>" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="create">
    <div class="row">
      <?= field('name', t('Name'), '', 'text', ['required' => true, 'placeholder' => 'Ultegra Di2 groupset', 'maxlength' => 160]) ?>
      <?= field('price', t('Price paid'), '', 'text', ['inputmode' => 'decimal']) ?>
      <?= field('merchant', t('Shop'), '', 'text', ['list' => 'shops']) ?>
      <?= field('purchased_on', t('Bought on'), '', 'date') ?>
    </div>
    <fieldset><legend><?= h(t('Parts (only parts without their own price)')) ?></legend>
      <?php foreach ($candidates as $c): ?>
        <label class="check"><input type="checkbox" name="parts[]" value="<?= (int)$c['id'] ?>"> <?= h(Domain::componentName($c)) ?> <span class="muted"><?= h(Catalog::typeName($c['component_type'])) ?></span></label>
      <?php endforeach; ?>
    </fieldset>
    <button class="btn primary"><?= h(t('Save bundle')) ?></button>
  </form>
  <?php endif; ?>
</section>
