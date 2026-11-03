<?php /* $entries, $bikeId, $componentId, $back */ ?>
<form method="post" action="<?= h(url('journal')) ?>" class="row"><?= Csrf::field() ?>
  <input type="hidden" name="do" value="add"><input type="hidden" name="back" value="<?= h($back) ?>">
  <input type="hidden" name="bike_id" value="<?= (int)$bikeId ?>"><input type="hidden" name="component_id" value="<?= (int)$componentId ?>">
  <?= field('entry_on', t('On'), today(), 'date', ['required' => true]) ?>
  <label><?= h(t('Kind')) ?><select name="kind"><?= options(['NOTE' => t('Note'), 'ISSUE' => t('Issue (to solve)')], 'NOTE') ?></select></label>
  <?= field('text', t('Text'), '', 'text', ['required' => true, 'maxlength' => 5000]) ?>
  <button class="btn small"><?= h(t('Add')) ?></button>
</form>
<table class="list">
<?php foreach ($entries as $e): ?>
  <tr class="<?= $e['voided_at'] ? 'voided' : '' ?>"><td><?= h($e['entry_on']) ?></td>
    <td><?= $e['kind'] === 'ISSUE' ? ($e['resolved_on'] ? status_badge('OK') : status_badge('SOON')) . ' ' : '' ?><?= h($e['text']) ?>
      <?= !$componentId && $e['part_label'] ? ' <span class="muted">· ' . h($e['part_label']) . '</span>' : '' ?></td>
    <td><?php if ($e['kind'] === 'ISSUE' && !$e['voided_at']): ?>
        <?= $e['resolved_on'] ? post_button('journal', [], t('Open again'), 'btn small', null, ['do' => 'reopen', 'id' => $e['id'], 'back' => $back])
            : post_button('journal', [], t('Solved'), 'btn small', null, ['do' => 'resolve', 'id' => $e['id'], 'back' => $back]) ?>
      <?php endif; ?>
      <?= $e['voided_at'] ? post_button('journal', [], t('Restore'), 'btn small', null, ['do' => 'restore', 'id' => $e['id'], 'back' => $back])
          : post_button('journal', [], t('Remove'), 'btn small', null, ['do' => 'void', 'id' => $e['id'], 'back' => $back]) ?></td></tr>
<?php endforeach; ?>
</table>
