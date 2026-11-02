<?php /** @var array $reminders  @var string $back  @var int $backId */ ?>
<?php if (!$reminders): ?>
  <p class="muted">Nothing due right now. Reminders appear for parts that are installed on a bike.</p>
<?php else: ?>
<ul class="reminders">
<?php foreach ($reminders as $r):
    $c = $r['component']; $b = $r['bike']; $rule = $r['rule'];
    $what = $c ? Domain::componentName($c) : 'Whole bike';
    $title = $r['kind'] === 'attention' ? 'Check result' : $rule['name'];
    $logParams = $c ? ['part' => $c['id']] : ['bike' => $b['id']];
    if ($rule) { $logParams['action'] = $rule['action_code']; }
?>
  <li class="rem s-<?= h(strtolower($r['status'])) ?>">
    <div class="rem-head">
      <?= status_badge($r['status']) ?>
      <strong><?= h($title) ?></strong>
      <span class="muted">· <?php if ($c): ?><a href="<?= h(url('part', ['id' => $c['id']])) ?>"><?= h($what) ?></a><?php else: ?><?= h($what) ?><?php endif; ?>
        on <a href="<?= h(url('bike', ['id' => $b['id']])) ?>"><?= h($b['name']) ?></a></span>
    </div>
    <p class="why"><?= h($r['text']) ?></p>
    <div class="rem-actions">
      <a class="btn small primary" href="<?= h(url('log', $logParams)) ?>">Log it</a>
      <?php if ($rule && $r['status'] !== 'OK'): ?>
        <details class="inline"><summary class="btn small">Snooze</summary>
          <form method="post" action="<?= h(url('snooze')) ?>" class="row">
            <?= Csrf::field() ?>
            <input type="hidden" name="rule_code" value="<?= h($rule['rule_code']) ?>">
            <input type="hidden" name="component_id" value="<?= h($c['id'] ?? '') ?>">
            <input type="hidden" name="bike_id" value="<?= h($b['id']) ?>">
            <input type="hidden" name="back" value="<?= h($back ?? 'reminders') ?>"><input type="hidden" name="back_id" value="<?= h($backId ?? '') ?>">
            <?php if ($r['status'] === 'SNOOZED'): ?>
              <button class="btn small" name="do" value="clear">End snooze</button>
            <?php else:
              preg_match('/^([\d ]+) km/', $r['text'], $m); $used = isset($m[1]) ? str_replace(' ', '', $m[1]) : '0'; ?>
              <input type="hidden" name="used_km" value="<?= h($used) ?>">
              <label>Days <input type="number" name="days" min="0" max="365" value="7"></label>
              <label>or km <input type="number" name="km" min="0" step="10"></label>
              <button class="btn small">Snooze</button>
              <small>Snoozing records no maintenance.</small>
            <?php endif; ?>
          </form>
        </details>
      <?php endif; ?>
    </div>
  </li>
<?php endforeach; ?>
</ul>
<?php endif; ?>
