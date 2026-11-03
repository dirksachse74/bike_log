<p class="muted"><?= h(t($list['hint'])) ?> <?= h(t('Type a shop once; after that you pick it. Renaming changes every record that uses the name. Merging puts two spellings together. Nothing is deleted: a hidden name stays on its records.')) ?></p>
<form method="post" action="<?= h(url('lists')) ?>" class="row card"><?= Csrf::field() ?><input type="hidden" name="do" value="add">
  <?= field('name', t('New shop'), '', 'text', ['required' => true, 'maxlength' => 160]) ?><button class="btn primary"><?= h(t('Add')) ?></button>
</form>
<?php $active = array_filter($rows, fn($r) => !$r['merged_into_id']); ?>
<table class="list">
  <thead><tr><th><?= h(t('Name')) ?></th><th class="num"><?= h(t('Used')) ?></th><th></th></tr></thead>
  <?php foreach ($rows as $r): ?>
  <tr class="<?= $r['hidden_at'] || $r['merged_into_id'] ? 'retired' : '' ?>">
    <td><?= h($r['name']) ?><?= $r['merged_into_id'] ? ' <span class="muted">→ ' . h(t('merged into {name}', ['name' => $r['merged_into']])) . '</span>' : ($r['hidden_at'] ? ' <span class="muted">' . h(t('hidden')) . '</span>' : '') ?></td>
    <td class="num"><?= (int)$r['uses'] ?></td>
    <td>
      <?php if (!$r['merged_into_id']): ?>
      <details><summary class="btn small"><?= h(t('Change')) ?></summary>
        <form method="post" action="<?= h(url('lists', ['id' => $r['id']])) ?>" class="row"><?= Csrf::field() ?><input type="hidden" name="do" value="rename">
          <?= field('name', t('Rename to'), $r['name'], 'text', ['required' => true, 'maxlength' => 160]) ?><button class="btn small"><?= h(t('Rename')) ?></button></form>
        <?php if (count($active) > 1): ?>
        <form method="post" action="<?= h(url('lists', ['id' => $r['id']])) ?>" class="row" data-confirm="<?= h(t('Move every record to the other name?')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="merge">
          <label><?= h(t('Merge into')) ?><select name="into"><?php foreach ($active as $o): if ((int)$o['id'] === (int)$r['id']) { continue; } ?><option value="<?= (int)$o['id'] ?>"><?= h($o['name']) ?></option><?php endforeach; ?></select></label>
          <button class="btn small"><?= h(t('Merge')) ?></button></form>
        <?php endif; ?>
        <?= post_button('lists', ['id' => $r['id']], $r['hidden_at'] ? t('Offer again') : t('Hide from the lists'), 'btn small link', null, ['do' => $r['hidden_at'] ? 'show' : 'hide']) ?>
      </details>
      <?php endif; ?>
    </td>
  </tr>
  <?php endforeach; ?>
</table>
