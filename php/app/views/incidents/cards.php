<?php /* $incidents, $fixData, $back */ ?>
<?php foreach ($incidents as $inc): ?>
<div class="card incident">
  <p><strong><?= h($inc['label']) ?></strong> · <?= h($inc['on']) ?>
    <?php if ($inc['ride_id']): ?> · <a href="<?= h(url('ride', ['id' => $inc['ride_id']])) ?>"><?= h($inc['ride_name'] ?: 'ride') ?></a><?php endif; ?>
    <?= $inc['bike_name'] ? ' · ' . h($inc['bike_name']) : '' ?>
    <?= $inc['resolved_on'] ? status_badge('OK') . ' <span class="muted">solved ' . h($inc['resolved_on']) . '</span>' : status_badge('SOON') ?></p>
  <?php if ($inc['text']): ?><p><?= h($inc['text']) ?></p><?php endif; ?>
  <table class="list">
  <?php foreach ($inc['affected'] as $a): $fd = $fixData[$a['id']] ?? null; ?>
    <tr><td><?= $a['component_id'] ? '<a href="' . h(url('part', ['id' => $a['component_id']])) . '">' . h(Domain::componentName(['label' => $a['part_label'], 'mark' => $a['mark'] ?? null])) . '</a>'
          : h($a['affected'] ?? 'Whole bike') ?></td>
      <td><?php if ($a['repair']): ?>
          <?= h(ucfirst((string)$a['repair_text'])) ?> <span class="muted"><?= h($a['repaired_on']) ?></span>
          <?= post_button('incident_fix', [], 'Undo fix', 'btn small', 'Undo this fix? Parts and stock go back to how they were.', ['do' => 'undo', 'entry' => $a['id'], 'back' => $back]) ?>
        <?php elseif (!$a['voided_at']): ?>
          <details class="inline"><summary class="btn small"><?= h(t('What did you do?')) ?></summary>
            <form method="post" action="<?= h(url('incident_fix')) ?>" class="card" data-fix><?= Csrf::field() ?>
              <input type="hidden" name="entry" value="<?= (int)$a['id'] ?>"><input type="hidden" name="back" value="<?= h($back) ?>">
              <label><?= h(t('What was done')) ?><select name="action" data-fix-action>
                <?= options(($fd && $fd['replaceable'] ? ['REPLACED' => 'Replaced it'] : []) + ['REPAIRED' => 'Repaired / adjusted it', 'NONE' => 'Nothing needed'], '') ?></select></label>
              <?php if ($fd && $fd['sources']): ?>
                <label data-fix-for="REPLACED"><?= h(t('Replaced with')) ?><select name="source"><?= options($fd['sources'], '') ?></select></label>
                <?php if ($fd['old_part']): ?>
                  <?= field('new_label', 'Name of the new part (if new)', '', 'text', ['maxlength' => 160, 'data-fix-for' => 'REPLACED']) ?>
                  <label data-fix-for="REPLACED"><?= h(t('The old part')) ?><select name="outcome"><?= options(Inventory::dispositions(), $fd['default_outcome']) ?></select></label>
                <?php endif; ?>
              <?php endif; ?>
              <?= field('on', 'On', $inc['on'] > today() ? $inc['on'] : max($inc['on'], today()), 'date', ['required' => true]) ?>
              <?= field('text', 'Note', '', 'text', ['maxlength' => 255]) ?>
              <button class="btn small primary"><?= h(t('Save')) ?></button>
            </form>
          </details>
        <?php endif; ?></td></tr>
  <?php endforeach; ?>
  </table>
  <div class="actions">
    <?php if (empty($inc['affected'][0]['voided_at'])): ?>
      <?= $inc['resolved_on'] ? post_button('incident', [], 'Open again', 'btn small', null, ['do' => 'reopen', 'group' => $inc['group'], 'back' => $back])
          : post_button('incident', [], 'Solved today', 'btn small', null, ['do' => 'solve', 'group' => $inc['group'], 'back' => $back]) ?>
      <?= post_button('incident', [], 'Remove', 'btn small', 'Remove this incident? You can restore it later.', ['do' => 'remove', 'group' => $inc['group'], 'back' => $back]) ?>
    <?php else: ?>
      <?= post_button('incident', [], 'Restore', 'btn small', null, ['do' => 'restore', 'group' => $inc['group'], 'back' => $back]) ?>
    <?php endif; ?>
  </div>
</div>
<?php endforeach; ?>
