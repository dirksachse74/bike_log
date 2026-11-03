<?php $bikeId = (int)$rot['bike']['id']; $chains = $rot['chains']; ?>
<?php if ($rot['prompt']): ?>
<div class="card"><p><?= status_badge('SOON') ?> <?= h($rot['prompt']['text']) ?></p>
  <?php if (in_array($rot['prompt']['kind'], ['SWAP', 'INSTALL'], true)): ?>
    <?= post_button('chain_do', ['bike' => $bikeId], $rot['prompt']['kind'] === 'SWAP' ? 'Swap now' : 'Put it on', 'btn primary', null, ['do' => 'swap', 'to' => $rot['prompt']['to'], 'on' => today()]) ?>
  <?php endif; ?>
</div>
<?php endif; ?>
<?php if ($rot['wax']): ?><p class="muted"><?= h($rot['wax']['text']) ?></p><?php endif; ?>

<table class="list">
  <thead><tr><th><?= h(t('Chain')) ?></th><th><?= h(t('State')) ?></th><th class="num"><?= h(t('Since hot wax')) ?></th><th class="num"><?= h(t('Lifetime')) ?></th><th class="num"><?= h(t('Hot waxes')) ?></th><th><?= h(t('Wear')) ?></th><th></th></tr></thead>
  <?php foreach ($chains as $c): ?>
  <tr><td><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h($c['label']) ?></a></td>
    <td><?= $c['state'] === 'READY_TO_INSTALL' ? status_badge('OK') . ' ' : '' ?><?= h($c['text']) ?></td>
    <td class="num"><?= $c['km_since_hot_wax'] === null ? '–' : h(km($c['km_since_hot_wax'])) ?></td>
    <td class="num"><?= h(km($c['lifetime_km'])) ?></td><td class="num"><?= (int)$c['wax_cycles'] ?></td>
    <td class="muted"><?= $c['last_wear'] ? h($c['last_wear']['date'] . ' ' . ($c['last_wear']['value'] !== null ? (float)$c['last_wear']['value'] . ' ' . $c['last_wear']['unit'] : Catalog::label((string)$c['last_wear']['outcome']))) : '–' ?></td>
    <td><?php if ($c['state'] !== 'INSTALLED' && !in_array($c['state'], ['WORN', 'RETIRED'], true)): ?>
        <?= post_button('chain_do', ['bike' => $bikeId], 'Put on', 'btn small', null, ['do' => 'swap', 'to' => $c['id'], 'on' => today()]) ?>
      <?php endif; ?>
      <?php if ($c['state'] !== 'INSTALLED'): ?><?= post_button('chain_do', ['bike' => $bikeId], 'Leave rotation', 'btn small link', null, ['do' => 'leave', 'id' => $c['id']]) ?><?php endif; ?></td></tr>
  <?php endforeach; ?>
</table>
<?php if (!$chains): ?><p class="muted"><?= h(t('No chain on this bike yet.')) ?></p><?php endif; ?>

<?php if ($chains): ?>
<section><h2><?= h(t('Hot wax')) ?></h2>
  <form method="post" action="<?= h(url('chain_do', ['bike' => $bikeId])) ?>" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="wax">
    <fieldset><legend><?= h(t('Chains waxed')) ?></legend>
      <?php foreach ($chains as $c): if (in_array($c['state'], ['WORN', 'RETIRED'], true)) { continue; } ?>
        <label class="check"><input type="checkbox" name="chains[]" value="<?= (int)$c['id'] ?>" <?= in_array($c['id'], $rot['dirty'], true) ? 'checked' : '' ?>> <?= h($c['label']) ?> <span class="muted"><?= h($c['text']) ?></span></label>
      <?php endforeach; ?>
    </fieldset>
    <div class="row">
      <?= field('on', 'On', today(), 'date', ['required' => true]) ?>
      <?php if ($waxes): ?><label><?= h(t('Wax')) ?><select name="consumable_id"><?= options(array_column($waxes, 'name', 'id'), '', true, 'Not tracked') ?></select></label>
        <?= field('qty', 'Amount used', '', 'text', ['inputmode' => 'decimal']) ?><?php endif; ?>
      <?php if ($rot['on']): ?><label><?= h(t('Swap first')) ?><select name="then_install"><?php $o = []; foreach ($chains as $c) { if ($c['state'] !== 'INSTALLED' && !in_array($c['state'], ['WORN', 'RETIRED'], true)) { $o[$c['id']] = 'Put ' . $c['label'] . ' on, so ' . $rot['on']['label'] . ' is waxed too'; } } ?><?= options($o, '', true, 'No swap') ?></select></label><?php endif; ?>
    </div>
    <button class="btn primary"><?= h(t('Save hot wax')) ?></button>
  </form>
</section>
<?php endif; ?>

<details><summary><?= h(t('Add a chain to this rotation')) ?></summary>
  <?php if ($rot['candidates']): ?>
  <form method="post" action="<?= h(url('chain_do', ['bike' => $bikeId])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="add">
    <label><?= h(t('Chain')) ?><select name="pick" required><?= options($rot['candidates'], '', true, 'Choose...') ?></select></label>
    <?= field('on', 'On', today(), 'date', ['required' => true]) ?>
    <button class="btn small"><?= h(t('Add')) ?></button>
  </form>
  <?php else: ?><p class="muted"><?= h(t('No free chain.')) ?> <a href="<?= h(url('part_edit', ['type' => 'CHAIN'])) ?>"><?= h(t('Add a chain')) ?></a> <?= h(t('or counted chain stock first.')) ?></p><?php endif; ?>
</details>

<details><summary><?= h(t('History')) ?></summary>
  <table class="list"><?php foreach ($rot['timeline'] as $t): ?>
    <tr><td><?= h($t['date']) ?></td><td><?= h($t['label']) ?></td>
      <td><?= $t['kind'] === 'ON' ? 'on the bike until ' . h($t['until'] ?? 'now') . ' · ' . h(km($t['km'])) : ($t['kind'] === 'WAX' ? 'hot wax' : 'liquid wax top-up') ?></td></tr>
  <?php endforeach; ?></table>
</details>
